from __future__ import annotations
import os
import re
from abc import ABC, abstractmethod
from typing import Optional

from iparser import IStateMachineParser
from ea_db_repository import BaseRepository, MockEAObject
from template import StateMachine, State, Transition, DiagramConfig, Trigger
from exceptions import DiagramNotFoundError, InvalidDiagramError

STATE_ORDER_BY = (
    "IIF(act.object_type IN ('State', 'StateMachine'), 0, 1) ASC, "
    "d.parentID ASC, "
    "(rectTop*rectTop + rectLeft*rectLeft) ASC, "
    "rectLeft ASC"
)

class EParser(IStateMachineParser, ABC):
    def __init__(self) -> None:
        self.repository: Optional[BaseRepository] = None
        
    @abstractmethod
    def connect(self, filename: str) -> BaseRepository:
        pass
    
    def check(self, filename: str, diagram_name: str) -> bool:
        """Checks if the diagram exists and is valid without generating the model."""
        if not filename:
            raise ValueError("filename must be a non-empty string")
        
        self.repository = self.connect(filename)
        
        try:
            exists = self.repository.diagram_exists(diagram_name)
            is_valid = self._has_initial_state(diagram_name)
            return exists and is_valid
        except Exception:
            self.repository.close()
            self.repository = None
            raise
    
    def parse(self, filename: str, diagram_name: str) -> StateMachine:
        if self.repository is None:
            self.repository = self.connect(filename)

        if not self.repository.diagram_exists(diagram_name):
            raise DiagramNotFoundError(f"Diagram '{diagram_name}' not found")
        if not self._has_initial_state(diagram_name):
            raise InvalidDiagramError(f"Diagram '{diagram_name}' is structurally invalid")
        
        sm = self.extract_model(diagram_name)
        self._write_model(sm, filename)
        return sm
    
    def _write_model(self, sm: StateMachine, filename: str) -> None:
        base_name = os.path.splitext(os.path.basename(filename))[0]
        output_path = os.path.join(sm.config.path, f"{base_name}_model.py")
        os.makedirs(sm.config.path, exist_ok=True)

        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.py")
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("####################################################\n")
            f.write("#      AUTO-GENERATED — do not modify manually     #\n")
            f.write("####################################################\n\n")
            f.write(template_content)
            f.write("\n\n")
            f.write(sm.to_code())

    def _extract_config(self, diagram_name: str) -> DiagramConfig:
        diagram      = self.repository.get_diagram_by_name(diagram_name)
        notes        = diagram.Notes        or "" if diagram else ""
        author       = diagram.Author       or "" if diagram else ""
        modified_date = diagram.ModifiedDate or "" if diagram else ""
        
        def _get(key: str) -> str:
            match = re.search(
                r"^\s*" + re.escape(key) + r"\s*=\s*(.+?)\s*$",
                notes, re.IGNORECASE | re.MULTILINE
            )
            return match.group(1) if match else ""

        path = _get("PATH")
        if not path or path in [".\\", "./"]:
            path = os.path.dirname(os.path.abspath(self.repository.ConnectionString))

        return DiagramConfig(
            path          = path,
            loop_time     = _get("LOOP_TIME")     or "1",
            event_prefix  = _get("EVENT_PREFIX"),
            state_prefix  = _get("STATE_PREFIX"),
            action_prefix = _get("ACTION_PREFIX"),
            guard_prefix  = _get("GUARD_PREFIX"),
            author        = author,
            modified_date = str(modified_date),
        )

    def _extract_triggers(self, diagram_name: str) -> list[Trigger]:
        elements = self.repository.get_element_set("SELECT object_id FROM t_object WHERE object_type = ?", ("Trigger",))
        triggers = []
        seen     = set()

        for ea_el in elements:
            if not ea_el or ea_el.Name in seen:
                continue
            seen.add(ea_el.Name)

            trigger_type  = "NULL"
            trigger_value = 0

            for prop in ea_el.CustomProperties: 
                if prop.Value == "Time":
                    trigger_type  = "HSM_TIMING"
                    trigger_value = self._get_timing_value(ea_el.Name)
                elif prop.Value == "Call":
                    trigger_type  = "HSM_CALLBACK"
                elif prop.Value == "Signal":
                    trigger_type  = "HSM_SIGNAL"
                elif prop.Value == "Change":
                    print(f"WARNING! Trigger '{ea_el.Name}' uses type 'Change' which is not supported")
            
            if trigger_type == "NULL":
                print(f"WARNING! Trigger '{ea_el.Name}' has no type defined in EA")

            triggers.append(Trigger(
                name         = ea_el.Name,
                trigger_type = trigger_type,
                value        = trigger_value,
            ))

        return triggers
    
    def _recursive_extract(self, hsm_name: str, query: str, parent_id: int, sm_obj: StateMachine) -> None:
        """Process hierarchy levels."""
        for ea_el in self.repository.get_element_set(query):
            new_state = State(
                element_id=ea_el.ElementID,
                name=ea_el.Name,
                parent_id=parent_id,
                state_type=ea_el.Type,
                ntype=ea_el.NType
            )

            self._fill_operations(ea_el.ElementID, new_state)
            self._fill_transitions(ea_el.ElementID, new_state, hsm_name)
            sm_obj.add_state(new_state)
            
            if ea_el.Type == "StateMachine":
                sql_sub = (
                    f"SELECT act.Object_ID FROM ((t_object act "
                    f"INNER JOIN t_diagramobjects dobj ON dobj.Object_ID = act.Object_ID) "
                    f"INNER JOIN t_diagram d ON d.Diagram_ID = dobj.Diagram_ID) "
                    f"WHERE d.parentId = {ea_el.ElementID} "  
                    f"AND act.Object_id <> d.parentId "
                    f"AND act.NType IN (0,3,4,8,13) "
                    f"AND act.object_type IN ('StateMachine','State','StateNode', 'ExitPoint') "
                    f"ORDER BY {STATE_ORDER_BY}"
                )
                if self.repository.get_element_set(sql_sub):
                    self._recursive_extract(hsm_name, sql_sub, ea_el.ElementID, sm_obj)

            elif ea_el.Type == "State":
                sql_border = (
                    f"SELECT object_id FROM t_object "
                    f"WHERE parentId = {ea_el.ElementID} "
                    f"AND object_type = 'ExitPoint'"
                )
                for border_el in self.repository.get_element_set(sql_border):
                    border_state = State(
                        element_id=border_el.ElementID,
                        name=border_el.Name,
                        parent_id=ea_el.ElementID,
                        state_type=border_el.Type,
                        ntype=border_el.NType
                    )
                    self._fill_transitions(border_el.ElementID, border_state, hsm_name)
                    sm_obj.add_state(border_state)
                
                sql_sub = (
                    f"SELECT act.Object_ID FROM ((t_object act "
                    f"INNER JOIN t_diagramobjects dobj ON dobj.Object_ID = act.Object_ID) "
                    f"INNER JOIN t_diagram d ON d.Diagram_ID = dobj.Diagram_ID) "
                    f"WHERE act.parentId = {ea_el.ElementID} "  
                    f"AND act.Object_id <> d.parentId "
                    f"AND act.NType IN (0,3,4,8,13) "
                    f"AND act.object_type IN ('StateMachine','State','StateNode') "
                    f"ORDER BY {STATE_ORDER_BY}"
                )
                if self.repository.get_element_set(sql_sub):
                    self._recursive_extract(hsm_name, sql_sub, ea_el.ElementID, sm_obj)

    def extract_model(self, diagram_name: str) -> StateMachine:
        """Extract the state machine model from the diagram."""
        sm = StateMachine(name=diagram_name)
        sm.config  = self._extract_config(diagram_name)

        sql_states = (
            f"SELECT act.Object_ID FROM ((t_object act "
            f"INNER JOIN t_diagramobjects dobj ON dobj.Object_ID = act.Object_ID) "
            f"INNER JOIN t_diagram d ON d.Diagram_ID = dobj.Diagram_ID) "
            f"WHERE d.Name = '{diagram_name}' AND act.Object_id <> d.parentId "
            f"AND act.parentId = d.parentId "  
            f"AND act.NType IN (0,3,4,8,13) AND act.object_type IN ('StateMachine','State','StateNode', 'ExitPoint') "
            f"ORDER BY {STATE_ORDER_BY}"
        )

        
        self._recursive_extract(diagram_name, sql_states, parent_id=None, sm_obj=sm)
        sm.triggers = self._extract_triggers(diagram_name)
        return sm
    
    def get_initial_id(self, elementId: int, diagram_name: str) -> int:
        sqlGetInitial = (
            f"SELECT act.Object_ID FROM ((t_object act "
            f"INNER JOIN t_diagramobjects dobj ON dobj.Object_ID = act.Object_ID) "
            f"INNER JOIN t_diagram d ON d.Diagram_ID = dobj.Diagram_ID) "
            f"WHERE act.parentId = {elementId} AND act.Object_id <> d.parentId "
            f"AND act.NType = 3 AND d.Name = '{diagram_name}'"
        )
        initial = self.repository.get_element_set(sqlGetInitial)
        for init in initial:
            sqlGetInitialConnector = (
                f"SELECT c.Connector_ID FROM t_connector c "
                f"WHERE c.Start_Object_ID={init.ElementID} "
                f"AND c.End_Object_ID IN ("
                f"SELECT dobj.Object_ID FROM t_diagramobjects dobj "
                f"INNER JOIN t_diagram d ON d.Diagram_ID = dobj.Diagram_ID "
                f"WHERE d.Name = '{diagram_name}') "
                f"AND c.End_Object_ID NOT IN (SELECT object_id FROM t_object WHERE Object_Type='StateNode' AND NType NOT IN (4)) "
                f"ORDER BY IIF(StereoType IS NOT NULL, 0, 1), StereoType, c.Connector_ID DESC"
            )
            connectorInitial = self.repository.get_connector_set(sqlGetInitialConnector)
            for conn in connectorInitial:
                return conn.SupplierID
        return 0

    def _fill_operations(self, element_id: int, state_obj: State) -> None:
        ops = self.repository.get_operation_set("SELECT operationId FROM t_operation WHERE object_id = ?", (element_id,))
        for op in ops:
            if op.ReturnType == "entry": state_obj.entry = op.Name
            elif op.ReturnType == "exit": state_obj.exit = op.Name
            elif op.ReturnType == "do": state_obj.do = op.Name

    def _fill_transitions(self, element_id: int, state_obj: State, diagram_name: str) -> None:
        sql = (
            f"SELECT c.Connector_ID FROM t_connector c WHERE c.Start_Object_ID={element_id} "
            f"AND c.End_Object_ID IN (SELECT object_id FROM t_object "
            f"WHERE (Object_Type IN ('State','StateMachine', 'ExitPoint') OR "
            f"(Object_Type='StateNode' AND NType IN (4,13))))"
            f"ORDER BY c.Connector_ID DESC"
        )
        connectors = self.repository.get_connector_set(sql)

        for conn in connectors:
            target_id = conn.SupplierID
            dest_ea   = self.repository.get_element_by_id(target_id)

            if dest_ea and dest_ea.Type == "StateMachine":
                dest_ea   = self.replace_destination(dest_ea.ElementID)
                target_id = dest_ea.ElementID if dest_ea else target_id

            if dest_ea and dest_ea.Type == "State":
                composite_id = target_id
                last_id      = target_id
                while composite_id > 0:
                    last_id      = composite_id
                    composite_id = self.get_initial_id(composite_id, diagram_name)  
                target_id = last_id

            events = [e.strip() for e in conn.TransitionEvent.split(",") if e.strip()] if conn.TransitionEvent else []
            t = Transition(
                connector_id = conn.ConnectorID,
                source_id    = element_id,
                target_id    = target_id,
                events       = events,
                guard        = conn.TransitionGuard,
                action       = conn.TransitionAction,
            )
            state_obj.add_transition(t)

    def _get_timing_value(self, trigger_name: str) -> int:
        raw = self.repository.get_timing_raw(trigger_name)
        if not raw:
            return 0
        parts = raw.split("RefName=")
        if len(parts) == 2:
            val = parts[1].split(";")[0]
            if val == "-1":
                return 0
            if val == "0":
                print(f"Error! Time value cannot be 0 ({trigger_name})")
            try:
                return int(val)
            except ValueError:
                return 0
        return 0

    def _has_initial_state(self, name: str) -> bool:
        return self.search_init_state_id(name) != 0

    def replace_destination(self, elementID: int) -> Optional[MockEAObject]:
        sql = (
            f"SELECT c.Connector_ID from t_connector c WHERE c.Start_Object_ID in"
            f" (SELECT act.Object_id from ((t_object act INNER JOIN t_diagramobjects dobj ON dobj.Object_ID = act.Object_ID)"
            f" INNER JOIN t_diagram d ON d.Diagram_ID = dobj.Diagram_ID)"
            f" WHERE d.parentId={elementID} AND act.NType IN (3,13))"
        )
        connectors = self.repository.get_connector_set(sql)
        return self.repository.get_element_by_id(connectors[0].SupplierID) if connectors else None

    def search_init_state_id(self, hsmName: str) -> int:
        sql_initials = (
            f"SELECT act.Object_ID FROM ((t_object act "
            f"INNER JOIN t_diagramobjects dobj ON dobj.Object_ID = act.Object_ID)"
            f"INNER JOIN t_diagram d ON d.Diagram_ID = dobj.Diagram_ID)"
            f"WHERE d.Name = '{hsmName}' AND act.Object_id <> d.parentId AND act.NType = 3"
        )
        initials = self.repository.get_element_set(sql_initials)
        if not initials: 
            return 0

        diagram_element_ids = self.repository.get_element_ids_in_diagram(hsmName)

        initial_id = 0
        for init in initials:
            if init.ParentID not in diagram_element_ids:
                initial_id = init.ElementID
                break
        
        if initial_id == 0:
            initial_id = initials[0].ElementID
        
        if initial_id != 0:
            sql_conn = f"SELECT c.Connector_ID FROM t_connector c WHERE c.Start_Object_ID ={initial_id}"
            conns = self.repository.get_connector_set(sql_conn)
            return conns[0].SupplierID if conns else 0
            
        return 0

    def close(self) -> None:
        if self.repository:
            self.repository.close()