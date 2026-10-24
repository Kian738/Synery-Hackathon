import { useState } from "react";

interface Props {
  onClose: () => void;
  onBuilt: (buildingId: string, report: any) => void;
}

const guessLevel = (name: string, index: number) => {
  const match = name.match(/floor[_ -]?(-?\d+)/i) ?? name.match(/(-?\d+)/);
  return match ? Number(match[1]) : index;
};

/** Level 4: upload one plan image per floor, give one real dimension, get a navigable building. */
export function BuildDialog({ onClose, onBuilt }: Props) {
  const [files, setFiles] = useState<{ file: File; level: number }[]>([]);
  const [width, setWidth] = useState("");
  const [name, setName] = useState("New building");
  const [vision, setVision] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = (list: FileList | null) => {
    if (!list) return;
    setFiles([...list].map((file, i) => ({ file, level: guessLevel(file.name, i) })).sort((a, b) => a.level - b.level));
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    const form = new FormData();
    files.forEach(({ file }) => form.append("files", file));
    form.append("levels", files.map((f) => f.level).join(","));
    form.append("width_m", width);
    form.append("name", name);
    form.append("vision", String(vision));
    try {
      const response = await fetch("/api/build", { method: "POST", body: form });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
      onBuilt(body.building_id, body.report);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>New building from floor plans</h3>
        <p className="muted">One image per floor. We find rooms, doors, entrances, stairs and lifts, and stack the floors.</p>
        <input type="file" accept="image/png,image/jpeg" multiple onChange={(e) => pick(e.target.files)} />
        {files.map((f, i) => (
          <div key={f.file.name} className="file-row">
            <span>{f.file.name}</span>
            <label>level <input type="number" value={f.level} onChange={(e) => setFiles(files.map((x, j) => (j === i ? { ...x, level: Number(e.target.value) } : x)))} /></label>
          </div>
        ))}
        <label className="field">Name <input value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field">How wide is the ground floor, in metres? <input value={width} onChange={(e) => setWidth(e.target.value)} placeholder="e.g. 55.5" /></label>
        <label className="toggle"><input type="checkbox" checked={vision} onChange={(e) => setVision(e.target.checked)} /> Read room names with Claude vision</label>
        {error && <p className="error-text">{error}</p>}
        <div className="preview-actions">
          <button className="primary" disabled={busy || !files.length || !Number(width)} onClick={submit}>{busy ? "Building…" : "Build"}</button>
          <button onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
