"""Background jobs the UI polls: a video transcode, a push."""
from .. import jobs
from ..errors import ApiError
from ..routes import Route


def get_job(req):
    job = jobs.get(req.params["job"])
    if job is None:
        raise ApiError(404, "not_found", "That job is not known here: the admin may have restarted since it began.")
    return job.view()


ROUTES = [
    Route("GET", r"jobs/(?P<job>[0-9a-f]{16})", get_job),
]
