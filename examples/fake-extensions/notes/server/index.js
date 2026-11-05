// Synthetic stand-in, not the upstream server. apply-patch.sh finds a folder by
// this fingerprint line, then checks the version and whether the diff applies.
const server = { name: "Apple-Notes-Server", version: "0.0.0" };
export default server;
