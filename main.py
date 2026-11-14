from Backend.TaskCreator import TaskCreator
from Database.Database import Database


if __name__ == "__main__":
    # tasks = TaskCreator().create_task()
    
    database = Database()
    # database.save_tasks(tasks)
    
    tasks = database.get_tasks()
    for task in tasks:
        print(task)
