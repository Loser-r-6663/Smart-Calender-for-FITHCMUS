import uuid
import psycopg2
from pydantic import ValidationError

from Database.db_config import get_database_config
from Database.daily_task_objects import DailyTaskObject
from Database.tasks import TaskRepository


class DatabaseManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        host=None,
        database=None,
        user=None,
        password=None,
        port=None,
    ):
        if self._initialized:
            return

        config = get_database_config()
        self.host = host if host is not None else config["host"]
        self.database = database if database is not None else config["database"]
        self.user = user if user is not None else config["user"]
        self.password = password if password is not None else config["password"]
        self.port = port if port is not None else config["port"]
        self.connection = None

        self.connect()
        self._initialized = True

    def connect(self):
        try:
            self.connection = psycopg2.connect(
                host=self.host,
                database=self.database,
                user=self.user,
                password=self.password,
                port=self.port,
            )
            print(" [DatabaseManager] Kết nối cơ sở dữ liệu thành công.")
        except Exception as error:
            print(f" [DatabaseManager] Lỗi kết nối cơ sở dữ liệu: {error}")
            raise

    def create_task(self, user_id, task_data, work_date):
        try:
            task_id = str(uuid.uuid4())
            TaskRepository().create(
                self.connection,
                {
                    **task_data,
                    "id": task_id,
                    "type": task_data.get("type", "personal"),
                },
            )
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO user_tasks (user_id, task_id)
                    VALUES (%s, %s)
                    """,
                    (user_id, task_id),
                )
                cursor.execute(
                    """
                    INSERT INTO daily_tasks (work_date, task_id)
                    VALUES (%s, %s)
                    """,
                    (work_date, task_id),
                )

            self.connection.commit()
            print(
                f" [DatabaseManager] Tạo thành công task: "
                f"'{task_data.get('title')}' (ID: {task_id})"
            )
            return task_id
        except ValueError:
            self.connection.rollback()
            raise
        except Exception as error:
            self.connection.rollback()
            print(f" [DatabaseManager] Lỗi khi tạo task, đã rollback: {error}")
            return None

    def get_tasks_by_date(self, user_id, work_date):
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT
                    t.*,
                    dt.work_date,
                    dt.is_completed_today
                FROM tasks t
                JOIN user_tasks ut ON t.id = ut.task_id
                JOIN daily_tasks dt ON t.id = dt.task_id
                WHERE ut.user_id = %s AND dt.work_date = %s
                """,
                (user_id, work_date),
            )
            columns = [column[0] for column in cursor.description]
            results = [
                DailyTaskObject.from_record(dict(zip(columns, row)))
                for row in cursor.fetchall()
            ]

            print(
                f" [DatabaseManager] Lấy thành công {len(results)} task "
                f"cho ngày {work_date}."
            )
            return results
        except ValidationError:
            raise
        except Exception as error:
            print(f" [DatabaseManager] Lỗi khi truy vấn task: {error}")
            return []
        finally:
            cursor.close()

    def update_task(self, task_id, update_data):
        if not update_data:
            print(
                " [DatabaseManager] Không có dữ liệu nào "
                "được cung cấp để cập nhật."
            )
            return False

        try:
            updated_task = TaskRepository().update(
                self.connection, task_id, update_data
            )
            self.connection.commit()
            if updated_task is None:
                return False
            print(
                f" [DatabaseManager] Cập nhật thành công task (ID: {task_id})"
            )
            return True
        except ValueError:
            self.connection.rollback()
            raise
        except Exception as error:
            self.connection.rollback()
            print(
                f" [DatabaseManager] Lỗi khi cập nhật task, "
                f"đã rollback: {error}"
            )
            return False

    def delete_task(self, task_id):
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "DELETE FROM daily_tasks WHERE task_id = %s",
                (task_id,),
            )
            cursor.execute(
                "DELETE FROM user_tasks WHERE task_id = %s",
                (task_id,),
            )
            cursor.execute("DELETE FROM tasks WHERE id = %s", (task_id,))

            self.connection.commit()
            print(f" [DatabaseManager] Xóa thành công task (ID: {task_id})")
            return True
        except Exception as error:
            self.connection.rollback()
            print(f" [DatabaseManager] Lỗi khi xóa task, đã rollback: {error}")
            return False
        finally:
            cursor.close()

    def close(self):
        if self.connection and not self.connection.closed:
            try:
                self.connection.commit()
                self.connection.close()
                print(" [DatabaseManager] Đã ngắt kết nối PostgreSQL an toàn.")
            except Exception as error:
                print(f" [DatabaseManager] Lỗi khi đóng kết nối: {error}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()