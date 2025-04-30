class ResumeOptimizerStateMachine:
    def __init__(self):
        self.state = "start"
        self.transitions = {
            "start": {
                "select_user": ("waiting_job_description", "User setup finished."),
            },
            "waiting_job_description": {
                "job_description_uploaded": ("processing_llm", "Job description selected. Starting processing..."),
            },
            "processing_llm": {
                "finished": ("job_exploration", "Loading..."),
            },
            "job_exploration": {
                "menu": ("start", "Loading the system again"),
            }
        }

    def next(self, event):
        if event in self.transitions.get(self.state, {}):
            next_state, message = self.transitions[self.state][event]
            self.state = next_state
            return message
        else:
            return f"Event: '{event}' -> is not valid for actual state: '{self.state}'."

    def reset(self):
        self.state = "start"