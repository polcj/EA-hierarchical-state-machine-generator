import os
from ea_db_repository import BaseRepository, DictRow, IS_WINDOWS
from eparser import EParser
from exceptions import RepositoryConnectionError

try:
    import pyodbc
    PYODBC_AVAILABLE: bool = True
except ImportError:
    PYODBC_AVAILABLE: bool = False

try:
    import jpype
    import jpype.imports
    import glob
    JPYPE_AVAILABLE: bool = True
except ImportError:
    JPYPE_AVAILABLE: bool = False

class AccessRepository(BaseRepository):
    def __init__(self, db_path) -> None:
        if not PYODBC_AVAILABLE:
            raise RepositoryConnectionError("pyodbc is not installed. Run: pip install pyodbc")
        # Legacy 32-bit driver that supports Jet 3 (Access 97)
        conn_str = (
            r"Driver={Microsoft Access Driver (*.mdb)};"
            f"DBQ={db_path};"
        )
        self.conn             = pyodbc.connect(conn_str)
        self.cursor           = self.conn.cursor()
        self.ConnectionString = db_path

    def _execute(self, query: str, params: tuple = ()) -> list[DictRow]:
        """Executes query and returns list of DictRow."""
        self.cursor.execute(query, params)
        columns = [col[0] for col in self.cursor.description]
        return [DictRow(columns, row) for row in self.cursor.fetchall()]

class UCanAccessRepository(BaseRepository):
    def __init__(self, db_path) -> None:
        if not JPYPE_AVAILABLE:
            raise RepositoryConnectionError(
                "jpype1 is not installed. Run: sudo apt install python3-jpype\n"
                "Also ensure UCanAccess jars are in a 'jars' folder next to this script."
            )

        # Start JVM if not already started, loading all jars from 'jars' folder
        if not jpype.isJVMStarted():
            jar_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jars", "*.jar")
            jars     = glob.glob(jar_path)
            if not jars:
                raise FileNotFoundError(
                    f"No .jar files found in {jar_path}\n"
                    "Download UCanAccess and its dependencies into a 'jars' folder next to this script."
                )
            jpype.startJVM(classpath=jars)

        # Force UCanAccess driver loading
        from java.sql import DriverManager
        jpype.JClass("net.ucanaccess.jdbc.UcanaccessDriver")

        self.ConnectionString = db_path
        self.conn             = DriverManager.getConnection(f"jdbc:ucanaccess://{db_path}")

    def _execute(self, query: str, params: tuple = ()) -> list[DictRow]:
        """Executes query using JDBC and returns a list of DictRow."""
        results = []
        stmt = None
        rs = None
        
        try:
            if params:
                stmt = self.conn.prepareStatement(query)
                for i, param in enumerate(params):
                    stmt.setObject(i + 1, param)
                rs = stmt.executeQuery()
            else:
                stmt = self.conn.createStatement()
                rs   = stmt.executeQuery(query)

            # Extract column names and force to Python strings
            meta      = rs.getMetaData()
            col_count = meta.getColumnCount()
            columns   = [str(meta.getColumnName(i)) for i in range(1, col_count + 1)]

            while rs.next():
                row_data = []
                for i in range(1, col_count + 1):
                    val = rs.getObject(i)
                    # Convert Java strings to Python strings
                    if val is not None and "java.lang.String" in str(type(val)):
                        val = str(val)
                    elif val is not None:
                        # Convert Java numeric types to Python int/float
                        try:
                            val = int(val)
                        except (TypeError, ValueError):
                            try:
                                val = float(val)
                            except (TypeError, ValueError):
                                val = str(val) if val is not None else None
                    row_data.append(val)
                results.append(DictRow(columns, row_data))
                
        finally:
            if rs is not None:
                rs.close()
            if stmt is not None:
                stmt.close()

        return results
    
class E13Parser(EParser):
    def connect(self, filename: str) -> BaseRepository:
        if IS_WINDOWS:
            self.repository = AccessRepository(filename)
        else:
            self.repository = UCanAccessRepository(filename)
        
        return self.repository       