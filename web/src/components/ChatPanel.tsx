import { useEffect, useRef, useState } from "react";
import type { ChatItem } from "../types";
import { listen, speak, speechSupported } from "../voice";

const TOOL_LABEL: Record<string, (input: any) => string> = {
  building_overview: () => "Reading the building overview",
  search: (i) => `Searching for “${i.query}”${i.floor ? ` on ${i.floor}` : ""}`,
  room_info: (i) => `Looking at ${i.room}`,
  find_route: (i) => `Planning a route to ${i.destination}`,
  reachable_rooms: (i) => `Checking which rooms on ${i.floor} can be reached`,
  rank_rooms: (i) => `Comparing ${i.room_type} rooms on ${i.floor}`,
  nearest: (i) => `Finding the nearest ${i.what}`,
  remember_person: () => "Remembering your needs",
  set_closed: (i) => `${i.closed ? "Closing" : "Reopening"} ${i.element}`,
  add_door: (i) => `${i.confirm ? "Adding" : "Previewing"} a door: ${i.first_room} ↔ ${i.second_room}`,
  move_item: (i) => `Moving ${i.item} to ${i.to_room}`,
};

export function toolLabel(name: string, input: any): string {
  return (TOOL_LABEL[name] ?? (() => name))(input ?? {});
}

const EXAMPLES = [
  "Where is the 3D printer?",
  "I'm in a wheelchair. How do I get from the main entrance to the quality lab?",
  "The office lift is closed for maintenance. What changes?",
  "Route me to the canteen but avoid the production halls.",
];

interface Props {
  items: ChatItem[];
  busy: boolean;
  onSend: (text: string) => void;
  onApplyPreview: (data: any) => void;
  voiceOut: boolean;
  setVoiceOut: (on: boolean) => void;
}

export function ChatPanel({ items, busy, onSend, onApplyPreview, voiceOut, setVoiceOut }: Props) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const lastSpoken = useRef<number>(-1);

  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [items, busy]);
  useEffect(() => {
    const last = [...items].reverse().find((i) => i.role === "agent");
    if (voiceOut && last && last.id !== lastSpoken.current) {
      lastSpoken.current = last.id;
      speak(last.text);
    }
  }, [items, voiceOut]);

  const submit = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    onSend(trimmed);
    setText("");
  };

  const mic = () => {
    if (listening) return;
    setListening(true);
    listen(
      (partial) => setText(partial),
      (final) => { setListening(false); submit(final); },
      () => setListening(false),
    );
  };

  return (
    <aside className="chat">
      <div className="chat-log">
        {items.length === 0 && (
          <div className="chat-empty">
            <p>Ask about this building. Try:</p>
            {EXAMPLES.map((e) => (
              <button key={e} className="example" onClick={() => submit(e)}>{e}</button>
            ))}
          </div>
        )}
        {items.map((item) => {
          if (item.role === "tool") return <div key={item.id} className="tool-chip">{item.text}</div>;
          if (item.role === "understood")
            return (
              <div key={item.id} className="understood">
                <span className="understood-title">Understood</span>
                <span>{item.text}</span>
                {item.data?.constraints?.length > 0 && (
                  <div className="chips">{item.data.constraints.map((c: string) => <span key={c} className="chip">{c}</span>)}</div>
                )}
              </div>
            );
          if (item.role === "preview")
            return (
              <div key={item.id} className="preview-card">
                <strong>Proposed change</strong>
                <span>{item.text}</span>
                {!item.data.applied && (
                  <div className="preview-actions">
                    <button className="primary" onClick={() => onApplyPreview(item.data)}>Apply</button>
                    <button onClick={() => onApplyPreview({ ...item.data, cancel: true })}>Discard</button>
                  </div>
                )}
              </div>
            );
          return (
            <div key={item.id} className={`bubble ${item.role}`}>
              {item.text.split("\n").map((line, i) => <p key={i}>{line}</p>)}
            </div>
          );
        })}
        {busy && <div className="typing"><span /><span /><span /></div>}
        <div ref={end} />
      </div>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        {speechSupported() && (
          <button type="button" className={`icon${listening ? " live" : ""}`} onClick={mic} title="Speak">
            {listening ? "●" : "🎤"}
          </button>
        )}
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder={listening ? "Listening…" : "Where do you want to go?"} />
        <button type="submit" className="primary" disabled={busy || !text.trim()}>Send</button>
        <button type="button" className={`icon${voiceOut ? " on" : ""}`} onClick={() => setVoiceOut(!voiceOut)} title="Read answers aloud">
          {voiceOut ? "🔊" : "🔈"}
        </button>
      </form>
    </aside>
  );
}
