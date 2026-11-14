from Backend.TaskCreator import TaskCreator
from Backend.Validation import Validation
from Database.Database import Database


if __name__ == "__main__":
    extracted_tasks = TaskCreator().create_task()
    
    database = Database()
    retained_tasks = database.get_tasks()
    
    tasks = Validation().deduplicate_task(extracted_tasks, retained_tasks)
    print(tasks)
    
    new_tasks = [task for task in tasks if task not in retained_tasks]
    database.save_tasks(new_tasks)
