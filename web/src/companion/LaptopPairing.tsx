import type { CompanionHost } from "./useCompanionHost";
import {PairingQR} from "./PairingQR";
import "./companion.css";

export interface LaptopPairingProps {
  host: CompanionHost;
  /** Route where `<PhoneCompanion />` is mounted, default "/phone". */
  phonePath?: string;
  /** Override the address the phone should open (for example an https:// tunnel or mkcert URL you set up yourself). */
  phoneOrigin?: string;
  className?: string;
}

const isLoopback = (hostname: string) => hostname === "localhost" || hostname.startsWith("127.") || hostname === "::1" || hostname === "[::1]";

/** The address a phone on the same network can use. The code goes after # so it never appears in server logs. */
export function phoneUrl(host: CompanionHost, phonePath = "/phone", origin?: string): string {
  const here = typeof location !== "undefined" ? location : null;
  let base = origin ?? here?.origin ?? "";
  if (!origin && here && isLoopback(here.hostname) && host.lanAddresses[0]) base = `${here.protocol}//${host.lanAddresses[0]}${here.port ? `:${here.port}` : ""}`;
  return `${base}${phonePath}${host.code ? `#code=${host.code}` : ""}`;
}

/**
 * Pairing panel for the laptop: start, show the code, confirm the phone, see status, end.
 * Rendering it does nothing until the user presses "Pair a phone".
 */
export function LaptopPairing({ host, phonePath = "/phone", phoneOrigin, className }: LaptopPairingProps) {
  const active = host.state !== "idle" && host.state !== "ended";
  const url = phoneUrl(host, phonePath, phoneOrigin);
  const insecure = typeof window !== "undefined" && !window.isSecureContext;
  return (
    <section className={`cmp cmp-laptop ${className ?? ""}`} aria-label="Pair a phone">
      <h2>Phone companion</h2>
      {!active && (
        <>
          <p>Use a phone as a remote: it shows the current step in large type and can turn the view. This laptop keeps full control.</p>
          {host.ended && <p className="cmp-error" role="status">{host.ended}</p>}
          {host.error && <p className="cmp-error" role="alert">{host.error}</p>}
          <button className="cmp-btn primary" onClick={() => void host.start()}>Pair a phone</button>
        </>
      )}
      {active && (
        <>
          <div className="cmp-status" data-tone={host.phoneOnline ? "ok" : "warn"}>
            <span className="cmp-dot" aria-hidden="true" />
            <span role="status" aria-live="polite">{host.phoneOnline ? "Phone connected" : host.state === "reconnecting" ? "Reconnecting to the pairing service…" : "Waiting for a phone"}</span>
          </div>
          {host.pending.map(request => (
            <div key={request.request_id} className="cmp-panel" role="alertdialog" aria-label="Allow this phone?">
              <p>A phone wants to connect. Allow it only if it shows this number:</p>
              <p className="cmp-verify">{request.verify}</p>
              <div className="cmp-row two">
                <button className="cmp-btn primary" onClick={() => host.approve(request.request_id)}>Allow</button>
                <button className="cmp-btn" onClick={() => host.deny(request.request_id)}>Deny</button>
              </div>
            </div>
          ))}
          {!host.phoneOnline && host.code && (
            <div className="cmp-panel">
              <p>Scan with your phone camera on the same Wi-Fi.</p>
              <PairingQR url={url}/>
              <details><summary>Or enter the code manually</summary>
              <p className="cmp-link">{url.replace(/#code=\d+$/, "")}</p>
              <p className="cmp-code" aria-label={`Pairing code ${host.code.split("").join(" ")}`}>{host.code}</p>
              <p className="cmp-small">One use, valid for two minutes.</p>
              </details>
              <button className="cmp-btn quiet" onClick={host.newCode}>New code</button>
              {insecure && <p className="cmp-small">This page is not HTTPS, so phone motion look will be off; touch controls work. See the setup notes for HTTPS options.</p>}
            </div>
          )}
          {host.error && <p className="cmp-error" role="alert">{host.error}</p>}
          <button className="cmp-btn quiet" onClick={host.revoke}>End pairing</button>
        </>
      )}
    </section>
  );
}
