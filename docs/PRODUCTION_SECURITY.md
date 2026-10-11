# Production security requirements

This is an operator CLI, not a public service. Use a supported Python release and hashed dependency locks. Prefer short-lived AWS credentials from the default provider chain; do not commit access keys or report exports containing infrastructure information. Use least-privileged IAM, keep read-only/dry-run as the default, and review changes before any apply operation.

The optional dashboard is bound to loopback. Remote access needs your own authenticated HTTPS gateway and private report storage. Reports and traces can reveal AWS identifiers and workload behavior; choose explicit retention, access control and backup policies.
