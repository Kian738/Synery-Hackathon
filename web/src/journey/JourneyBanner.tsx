import { useNavigate } from "react-router";
import { clearJourney, clearRoute, currentIndoorLeg, nextLeg, setJourneyIndex } from "./journey";
import "./JourneyBanner.css";

/** Shown in the Navigator while a trip between buildings is running: where this leg ends and what comes next. */
export function JourneyBanner({ buildingId, routeFailed = false, atExit = false, guiding = false, onStartGuide }: {
  buildingId: string; routeFailed?: boolean; atExit?: boolean; guiding?: boolean; onStartGuide?: () => void;
}) {
  const navigate = useNavigate();
  const current = currentIndoorLeg(buildingId);
  if (!current || !current.active) return null;
  const { leg, index, total, result } = current;
  const outdoor = result.legs.find((l) => l.kind === "outdoor");
  const exiting = leg.role === "exit";
  const verb = { foot: "walk", wheelchair: "roll", bike: "cycle", car: "drive" }[result.mode];
  return (
    <aside className="fw-journey-banner" aria-label="Trip between buildings">
      <div>
        <small>Trip · step {index + 1} of {total}</small>
        <b>{exiting ? `You are in ${leg.building_name}` : `You are now in ${leg.building_name}`}</b>
        <span>
          {exiting
            ? (leg.trivial
              ? `You are already in the room with the exit: ${leg.door.label.replace("Entrance into ", "")}. Then we skip the ${outdoor ? Math.round(outdoor.distance_m) : ""} m ${verb} outside and bring you to ${result.to_building.name}.`
              : `From ${leg.from} to the exit door (${leg.door.label.replace("Entrance into ", "via ")}), ${Math.round(leg.distance_m)} m. Then we skip the ${outdoor ? Math.round(outdoor.distance_m) : ""} m ${verb} outside and bring you to ${result.to_building.name}.`)
            : `You came in through ${leg.door.label.replace("Entrance into ", "the entrance into ")}. From there to ${leg.to}, ${Math.round(leg.distance_m)} m.`}
        </span>
        {leg.route.steps.length > 0 && (
          <details open>
            <summary>{routeFailed ? "The map route is not available here. Directions:" : exiting ? "How to get from your room to the exit" : "How to get from the entrance to your room"}</summary>
            <ol>{leg.route.steps.map((step, i) => <li key={i}>{step}</li>)}</ol>
          </details>
        )}
      </div>
      <div className="fw-journey-actions">
        {exiting ? (
          atExit ? (
            <>
              <span className="fw-journey-status" role="status">Exit reached — teleporting…</span>
              <button type="button" className="primary" onClick={() => { setJourneyIndex(nextLeg(result, index)); navigate("/tunnel"); }}>Go now →</button>
            </>
          ) : (
            <>
              {onStartGuide && !guiding && <button type="button" className="primary" onClick={onStartGuide}>Start the guide</button>}
              <button type="button" onClick={() => { setJourneyIndex(nextLeg(result, index)); navigate("/tunnel"); }}>I'm at the exit — continue →</button>
            </>
          )
        ) : (
          <button type="button" className="primary" onClick={() => { clearRoute(); navigate(`/?building=${encodeURIComponent(buildingId)}&from=map`); }}>I've arrived ✓</button>
        )}
        <button type="button" onClick={() => { clearJourney(); navigate(`/?building=${encodeURIComponent(buildingId)}&from=map`); }}>End trip</button>
      </div>
    </aside>
  );
}
