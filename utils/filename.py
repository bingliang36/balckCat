import datetime


class GetFilename:
    def __init__(self, prefix="", suffix=""):
        self.prefix = prefix
        self.suffix = suffix

    def get_formatted_time(self):
        now = datetime.datetime.now()
        time_str = now.strftime("%y%m%d%H%M%S") + f"{now.microsecond // 10000:02d}"
        return time_str

    def get_filename(self, prefix="", suffix=""):
        if prefix == "":
            prefix = self.prefix
        if suffix == "":
            suffix = self.suffix
        return prefix + self.get_formatted_time() + suffix

