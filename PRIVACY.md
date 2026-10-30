# Privacy

Analytics report is a personal command line tool. It runs only on its author's own computer and
is used only by its author. It is not a hosted service and has no other users.

## What it accesses

When the author signs in with their Google account, the tool asks for two permissions:

- **AdMob reports** (`admob.report`): to read the author's own ad performance and earnings.
- **Send email** (`gmail.send`): to email the weekly report to the author. It cannot read, change
  or delete any email.

With its own read only service account it also reads the author's own Google Play Console
reports, Firebase Crashlytics data and Firestore feedback for the author's apps.

## What it does with the data

It builds one weekly report and emails it to the author. Nothing is sold, shared with anyone else,
or sent anywhere except the author's own inbox. Weekly totals are kept as numbers on the author's
computer to show trends; review and feedback text is never stored.

## Removing access

The author can revoke the tool's access at any time from their Google Account's
[third-party connections](https://myaccount.google.com/connections) page.

## Contact

Questions go to the [issue tracker](https://github.com/MantasDemenius/analytics-dashboard/issues)
of this repository.
