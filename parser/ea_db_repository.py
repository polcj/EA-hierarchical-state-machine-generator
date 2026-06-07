from __future__ import annotations
from abc import ABC, abstractmethod
import os
import re
import sys
import subprocess
from typing import Optional

IS_WINDOWS: bool = sys.platform.startswith("win")

if IS_WINDOWS:
    try:
        import winreg
        WINREG_AVAILABLE: bool = True
    except ImportError:
        WINREG_AVAILABLE: bool = False
else:
    WINREG_AVAILABLE: bool = False

def find_python32() -> Optional[str]:
    """
    Searches for a Python 32-bit installation using the Windows Python Launcher
    and the Windows registry. Returns the executable path or None if not found.
    Only relevant on Windows where pyodbc requires 32-bit Python for Jet 3 files.
    """
    if not IS_WINDOWS:
        return None

    try:
        result = subprocess.run(
            ["py", "-3-32", "-c", "import sys; print(sys.executable)"],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    if WINREG_AVAILABLE:
        try:
            for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                for base_path in [r"SOFTWARE\Python\PythonCore", r"SOFTWARE\WOW6432Node\Python\PythonCore"]:
                    try:
                        key = winreg.OpenKey(hive, base_path)
                        i   = 0
                        while True:
                            try:
                                version = winreg.EnumKey(key, i)
                                if version.endswith("-32"):
                                    subkey = winreg.OpenKey(key, version + r"\InstallPath")
                                    path, _ = winreg.QueryValueEx(subkey, "ExecutablePath")
                                    if os.path.exists(path):
                                        return path
                                i += 1
                            except OSError:
                                break
                    except (FileNotFoundError, OSError):
                        pass
        except Exception:
            pass

    return None

class DictRow:
    """
    Wrapper that mimics sqlite3.Row interface.
    Used by both AccessRepository (pyodbc) and UCanAccessRepository (JPype).
    """
    def __init__(self, columns, row) -> None:
        self._data = dict(zip(columns, row))
        self._values = list(self._data.values())  


    def __getitem__(self, key) -> object:
        if isinstance(key, int):
            return self._values[key]
        return self._data.get(key)

    def keys(self) -> list[str]:
        return self._data.keys()
    
class MockEAObject:
    """
    Adapts a SQLite/Access/UCanAccess row to an object with the same
    properties as EA COM objects, applying the discovered column mapping.
    """
    def __init__(self, row, obj_type, repo_instance) -> None:
        self._repo = repo_instance  
        row_lower = {str(k).lower(): row[k] for k in row.keys()}

        for key in row.keys():
            setattr(self, key, row[key])

        if obj_type == "Element":
            self.ElementID = row_lower.get('object_id', 0) or 0
            self.Name      = row_lower.get('name', "") or ""
            self.Type      = row_lower.get('object_type', "") or ""
            self.ParentID  = row_lower.get('parentid', 0) or 0
            self.NType     = row_lower.get('ntype', 0) or 0

        elif obj_type == "Connector":
            self.ConnectorID      = row_lower.get('connector_id', 0) or 0
            self.ClientID         = row_lower.get('start_object_id', 0) or 0
            self.SupplierID       = row_lower.get('end_object_id', 0) or 0
            self.TransitionEvent  = row_lower.get('pdata1', "") or ""
            self.TransitionGuard  = row_lower.get('pdata2', "") or ""
            self.TransitionAction = row_lower.get('pdata3', "") or ""

        elif obj_type == "Operation":
            self.Name       = row_lower.get('name', "") or ""
            self.ReturnType = row_lower.get('type', "") or ""

        elif obj_type == "Diagram":
            self.Name         = row_lower.get('name', "") or ""
            self.Notes        = row_lower.get('notes', "") or ""
            self.Author       = row_lower.get('author', "") or ""
            self.ModifiedDate = row_lower.get('modifieddate', "") or ""

    @property
    def CustomProperties(self) -> list[MockProperty]:
        """
        Emulates trigger.CustomProperties from EA COM.
        Trigger type (Call/Time) is stored in t_xref with Name='CustomProperties',
        in Description field with format @VALU=Call@ENDVALU or @VALU=Time@ENDVALU.
        """
        guid = (getattr(self, 'ea_guid', None) or
                getattr(self, 'EA_GUID', None) or "")
        if not guid:
            return []
        rows  = self._repo._execute(
            "SELECT Description FROM t_xref WHERE Client = ? AND Name = 'CustomProperties'",
            (guid,)
        )
        props = []
        for row in rows:
            val   = row[0] if row else None
            desc  = str(val) if val is not None else ""
            match = re.search(r'@VALU=(.*?)@ENDVALU', desc)
            if match:
                props.append(MockProperty("kind", match.group(1)))
        
        if not props:
            mof_rows = self._repo._execute(
                "SELECT Description FROM t_xref WHERE Client = ? AND Name = 'MOFProps'",
                (guid,)
            )
            if mof_rows:
                props.append(MockProperty("kind", "Signal"))
                
        return props

class MockProperty:
    def __init__(self, name: str, value: str) -> None:
        self.Name  = name
        self.Value = value
    
class BaseRepository(ABC):

    def __init__(self, db_path: str) -> None:
        self.ConnectionString = db_path
        self.conn = None
        self.cursor = None

    @abstractmethod
    def _execute(self, query: str, params: tuple = ()) -> list:
        pass
        
    def get_element_set(self, query: str, params: tuple = ()) -> list[MockEAObject]:
        """Executes query and returns list of MockEAObject type Element."""
        rows   = self._execute(query, params)
        result = []
        for row in rows:
            object_id = row[0]
            if object_id:
                full_rows = self._execute("SELECT * FROM t_object WHERE Object_ID = ?", (object_id,))
                if full_rows:
                    result.append(MockEAObject(full_rows[0], "Element", self))
        return result
    
    def get_element_ids_in_diagram(self, diagram_name: str) -> set[int]:
        """Returns a set of element IDs that are part of the given diagram name."""
        sql = (
            "SELECT act.Object_ID FROM ((t_object act "
            "INNER JOIN t_diagramobjects dobj ON dobj.Object_ID = act.Object_ID) "
            "INNER JOIN t_diagram d ON d.Diagram_ID = dobj.Diagram_ID) "
            "WHERE d.Name = ?"
        )
        rows = self._execute(sql, (diagram_name,))
        return {int(row[0]) for row in rows if row and row[0]}

    def diagram_exists(self, name: str) -> bool:
        rows = self._execute("SELECT Diagram_ID FROM t_diagram WHERE Name=?", (name,))
        return len(rows) >= 1

    def get_diagram_by_name(self, name: str) -> Optional[MockEAObject]:
        row = self._execute("SELECT * FROM t_diagram WHERE Diagram_type='Statechart' AND Name=?", (name,))
        return MockEAObject(row[0], "Diagram", self) if row else None

    def get_timing_raw(self, trigger_name: str) -> str:
        rows = self._execute(
            "SELECT Description FROM t_xref WHERE Name = 'MOFProps' AND Client IN "
            "(SELECT ea_guid FROM t_object WHERE Name=?)",
            (trigger_name,)
        )
        for row in rows:
            if row and row[0]:
                return str(row[0])
        return ""

    def get_diagram_by_id(self, diagram_id: int) -> Optional[MockEAObject]:
        row = self._execute("SELECT * FROM t_diagram WHERE Diagram_ID = ?", (diagram_id,))
        return MockEAObject(row[0], "Diagram", self) if row else None

    def get_element_by_id(self, element_id: int) -> Optional[MockEAObject]:
        row = self._execute("SELECT * FROM t_object WHERE Object_ID = ?", (element_id,))
        return MockEAObject(row[0], "Element", self) if row else None

    def get_connector_by_id(self, conn_id: int) -> Optional[MockEAObject]:
        row = self._execute("SELECT * FROM t_connector WHERE Connector_ID = ?", (conn_id,))
        return MockEAObject(row[0], "Connector", self) if row else None

    def get_method_by_id(self, method_id: int) -> Optional[MockEAObject]:
        row = self._execute("SELECT * FROM t_operation WHERE OperationID = ?", (method_id,))
        return MockEAObject(row[0], "Operation", self) if row else None

    def get_attribute_by_id(self, attr_id: int) -> Optional[MockEAObject]:
        row = self._execute("SELECT * FROM t_attribute WHERE ID = ?", (attr_id,))
        return MockEAObject(row[0], "Attribute", self) if row else None

    def get_connector_set(self, query: str, params: tuple = ()) -> list[MockEAObject]:
        rows = self._execute(query, params)
        return [self.get_connector_by_id(int(row[0])) for row in rows if row[0]]

    def get_operation_set(self, query: str, params: tuple = ()) -> list[MockEAObject]:
        rows = self._execute(query, params)
        return [self.get_method_by_id(int(row[0])) for row in rows if row[0]]

    def close(self) -> None:
        if self.conn:
            self.conn.close()