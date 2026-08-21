from typing import Any, Optional

from extensions import db
from foundations.models import User, AuditLog

def log_action(
    # define the parameters for the log_action function, which will create an audit log entry in the database

    actor_id: Optional[int], # the user who performed the action
    entity_type: str, #"Loan, Transaction, Customer_Profile, etc"
    entity_id: int, # primary key of the affected row
    action: str,# "create, update, delete, etc"
    before:Optional[dict[str, Any]] = None,#snapshot before the action was performed
    after:Optional[dict[str, Any]] = None,#snapshot after the action was performed
    organization_id: Optional[int] = None,# the organization the action was performed under, if not provided, will be inferred from the actor_id

) -> AuditLog:
    
    # validate the action parameter to ensure it is one of the allowed actions
    #validate at the boundary to ensure the input is ok before doing anything with it

    if action not in ("create", "update", "delete"):
        raise ValueError(f"Invalid action: {action}")

    # if organization_id is not provided, infer it from the actor_id

    if organization_id is None:

        # if actor_id is also None, raise an error since we cannot infer the organization
        if actor_id is None:
            raise ValueError("organization_id must be provided if actor_id is None")

        # fetch the actor from the database using the actor_id
        actor = db.session.get(User, actor_id)

        # if the actor is not found, raise an error
        if actor is None:
            raise ValueError(f"No such user for actor_id: {actor_id}")
        
        organization_id = actor.organization_id

    # create the audit log entry
    entry = AuditLog(
        organization_id=organization_id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
    )

    # add the entry to the session and commit it to the database
    db.session.add(entry)
    db.session.commit()

    return entry


