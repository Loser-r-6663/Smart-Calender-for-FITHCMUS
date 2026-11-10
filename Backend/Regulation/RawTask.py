from pydantic import BaseModel


class RawTask(BaseModel):
    Title: str = "N/A"           # Title of the post
    Type: str = "N/A"            # Type of the post (e.g., SHCD-SV đầu năm, HỌC BỔNG TÀI TRỢ)
    Description: str = "N/A"     # Description or brief summary of the post
    CreateDate: str = "N/A"      # Creation date of the post
    Duration: str = "N/A"        # Duration of the task or event
    Deadline: str = "N/A"        # Assignment deadline
    Course: str = "N/A"          # Course associated with the post
    Location: str = "N/A"        # Location of the event or task
    Content: str = "N/A"         # Full content of the post
    Link: str = "N/A"            # Link to the original post
    Platform: str = "N/A"        # Platform from which the post was crawled (e.g., Portal, Facebook)
    
    def update(self, **kwargs):
        """Update the attributes of the RawTask instance with the provided keyword arguments."""
        for key, value in kwargs.items():
            if key in self.model_fields: setattr(self, key, value)
        return self
    
    def __repr__(self):
        return (
            f"\nRawTask(\n"
                f"\tTitle: {self.Title.__repr__()}\n"
                f"\tType: {self.Type.__repr__()}\n"
                f"\tDescription: {self.Description.__repr__()}\n"
                f"\tCreateDate: {self.CreateDate.__repr__()}\n"
                f"\tDuration: {self.Duration.__repr__()}\n"
                f"\tDeadline: {self.Deadline.__repr__()}\n"
                f"\tCourse: {self.Course.__repr__()}\n"
                f"\tLocation: {self.Location.__repr__()}\n"
                f"\tContent: {self.Content.__repr__()}\n"
                f"\tLink: {self.Link.__repr__()}\n"
                f"\tPlatform: {self.Platform.__repr__()}\n"
            ")"
        )