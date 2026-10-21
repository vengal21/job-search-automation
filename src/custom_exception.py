class JobSkipException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class JobNotSuitableException(JobSkipException):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class ApplicationReviewRequired(Exception):
    """The application form is filled and waiting for the user's review."""
