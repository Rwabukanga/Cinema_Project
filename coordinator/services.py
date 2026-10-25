"""
The coordinator: runs the TWO-PHASE COMMIT protocol across Server A and Server B.

    beginTransaction()  -> write STARTED to the log
    Phase 1 (voting)    -> sendPrepare() to every participant, collectVotes()
    Decision            -> write COMMITTED or ABORTED to the log FIRST
    Phase 2 (decision)  -> sendCommit() or sendAbort() to every participant
    recover()           -> after a crash, finish every transaction left open

Failure scenarios you can switch on to demonstrate the protocol:
    "payment_server_down" -> Server B does not answer in Phase 1 (counts as a NO vote)
    "coordinator_crash"   -> the coordinator crashes after collecting all YES votes
                             but before writing its decision
"""
from payments import services as payments_server
from seats import services as seats_server
from seats.models import Seat

from .models import TransactionLog

SCENARIOS = [
    ("none", "Normal booking"),
    ("payment_server_down", "Simulate: Payment server (Server B) is down"),
    ("coordinator_crash", "Simulate: Coordinator crashes before deciding"),
]


class SimulatedCrash(Exception):
    """Raised to imitate the coordinator dying in the middle of the protocol."""


def begin_transaction(customer_id, seat_id):
    seat = Seat.objects.select_related("showtime").get(pk=seat_id)
    return TransactionLog.objects.create(
        customer_id=customer_id, seat_id=seat_id, amount=seat.showtime.ticket_price
    )


def send_prepare(log, scenario="none"):
    """Phase 1: ask every participant to prepare and collect their votes."""
    log.seat_vote, seat_msg = seats_server.prepare(log.txn_id, log.seat_id, log.customer_id)

    if scenario == "payment_server_down":
        # No answer before the timeout -> the coordinator treats it as a NO vote.
        log.payment_vote, pay_msg = False, "No answer from Server B (timeout)."
    else:
        log.payment_vote, pay_msg = payments_server.prepare(log.txn_id, log.customer_id, log.amount)

    log.message = f"Server A: {seat_msg}  Server B: {pay_msg}"
    log.save()
    return log.seat_vote and log.payment_vote


def send_commit(log):
    seats_server.commit(log.txn_id)
    payments_server.commit(log.txn_id)
    log.completed = True
    log.save()


def send_abort(log):
    seats_server.abort(log.txn_id)
    payments_server.abort(log.txn_id)
    log.completed = True
    log.save()


def book_ticket(customer_id, seat_id, scenario="none"):
    """Book one seat for one customer as a single distributed transaction."""
    log = begin_transaction(customer_id, seat_id)

    # ---- Phase 1: voting ----
    all_yes = send_prepare(log, scenario)

    if all_yes:
        log.state = TransactionLog.PREPARED
        log.save()
        if scenario == "coordinator_crash":
            raise SimulatedCrash(
                "Coordinator crashed after every participant voted YES. "
                "The seat and the money stay held until recovery runs."
            )
        # ---- Decision: written to the log BEFORE anyone is told ----
        log.state = TransactionLog.COMMITTED
        log.save()
        # ---- Phase 2: commit ----
        send_commit(log)
    else:
        log.state = TransactionLog.ABORTED
        log.save()
        # ---- Phase 2: abort (undo whatever was prepared) ----
        send_abort(log)

    return log


def recover():
    """
    Finish every transaction that was left open by a crash.

    - Decision COMMITTED already in the log -> re-send COMMIT (participants must obey).
    - No decision in the log (STARTED or PREPARED) -> nobody can have committed yet,
      so it is safe to ABORT ("presumed abort").
    Returns a list of (txn_id, action) pairs.
    """
    results = []
    for log in TransactionLog.objects.filter(completed=False):
        if log.state == TransactionLog.COMMITTED:
            send_commit(log)
            results.append((log.txn_id, "commit re-sent"))
        else:
            log.state = TransactionLog.ABORTED
            log.message = (log.message + "  Recovered: aborted (no decision was logged).").strip()
            log.save()
            send_abort(log)
            results.append((log.txn_id, "aborted"))
    return results
