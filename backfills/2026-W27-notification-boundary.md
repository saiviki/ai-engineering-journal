# The first real reminder was the first useful test

*Source week: 2026-W27 · June 29–July 5, 2026*

The reminder code already had five commits and 84 dry-run tests. It had never sent a reminder.

I cut the first live test to a single timed message sent to my phone. A user-level system timer on a small cloud box fired the publisher. The server accepted the message. The phone showed nothing.

The logs held the clue: four messages were stored correctly. The scheduler and publisher worked. The missing piece was the phone subscription and wake-up path.

The next day I moved the service off a public topic and onto a self-hosted endpoint with TLS and deny-all authentication. Authenticated publishing returned 200. Anonymous reads and writes returned 403. The token stayed on the host and out of the repository.

## What I learned

Dry runs proved individual code paths. They did not prove the system.

The real acceptance test crossed every boundary: clock, publisher, server, push service, phone. "The server accepted it" was an intermediate receipt, not completion.

The first real reminder was the first useful test.
