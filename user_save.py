from Database.Database import Database
from Backend.Regulation.User import User

if __name__ == "_main_":
    # Đảm bào các file state còn hạn trước khi chạy
    with open("Backend/Crawler/State/PortalState.json", "r") as f:
        portal_session = f.read()
    with open("Backend/Crawler/State/MoodleState.json", "r") as f:
        moodle_session = f.read()
    
    database = Database()
    database.save_user(
        User(
            username="Trần Minh Phi",
            password="Phi050107",
            portal_username="25127116",
            portal_password="Phi050107@",
            portal_session=portal_session,
            portal_status=True,
            moodle_session=moodle_session,
            moodle_status=True
        )
    )