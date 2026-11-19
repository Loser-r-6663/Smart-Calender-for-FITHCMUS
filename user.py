from Database.Database import Database
from Backend.Validator import Validator


if __name__ == "__main__":
    database = Database()
    public_tasks = database.get_tasks()
    
    database = Database(database.get_user(
        # NOTE: This is a temporary solution for testing purposes.
        username = input("Enter username: "),
        password = input("Enter password: ")
    ))
    personal_tasks = database.get_tasks()
    
    tasks = public_tasks + personal_tasks
    tasks = Validator().filter_expired_tasks(tasks)
    print(tasks)
