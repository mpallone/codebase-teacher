"""Celery tasks for async processing."""

from celery import Celery

celery_app = Celery("tasks", broker="redis://localhost:6379/0")


@celery_app.task
def send_welcome_email(user_id: int) -> None:
    """Send a welcome email to a new user."""
    # Implementation would go here
    pass


@celery_app.task
def generate_report(report_type: str) -> dict:
    """Generate a report asynchronously."""
    return {"type": report_type, "status": "completed"}
