from datetime import datetime
from app import db
from app.models import LatePenalty, FinancialRecord

def pay_penalty(penalty_id):
    penalty = LatePenalty.query.get_or_404(penalty_id)

    if penalty.status == "paid":
        return False

    penalty.status = "paid"
    penalty.paid_at = datetime.utcnow()

    record = FinancialRecord(
        source="late_penalty",
        reference_id=penalty.id,
        description=f"Late return penalty for {penalty.registration_number}",
        amount=penalty.amount
    )

    db.session.add(record)
    db.session.commit()
    return True
