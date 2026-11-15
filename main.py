from Backend.TaskCreator import TaskCreator
from Backend.Validator import Validator
from Database.Database import Database


if __name__ == "__main__":
    extracted_tasks = TaskCreator().create_task()
    
    database = Database()
    retained_tasks = database.get_tasks()
    
    validator = Validator()
    tasks = validator.deduplicate_task(extracted_tasks, retained_tasks)
    print(tasks)
    
    new_tasks = [task for task in tasks if task not in retained_tasks]
    database.save_tasks(new_tasks)
    
    expired_tasks = validator.filter_expired_tasks(tasks)
    database.delete_tasks(expired_tasks)
