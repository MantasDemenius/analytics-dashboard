Firebase work in this repo (reading Crashlytics and Firestore with a service account, service
account setup, console-side config) goes through the **Firebase plugin** (`firebase@firebase`)
first: load its skill for the product at hand (`firebase-crashlytics`, `firebase-firestore`,
`firebase-basics`, ...) before writing code against it, and use its MCP server's
`developerknowledge_*` tools to check Firebase facts before a decision rests on them. Its MCP server
can also read live Crashlytics and Firestore data, which is the quickest way to see what the
report should show while building it. This tool reads, never writes: no deploys, no rule changes,
no document updates against an app's Firebase project from here.
