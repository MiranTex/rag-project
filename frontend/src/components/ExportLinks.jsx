import { exportUrl } from "../api";

export default function ExportLinks({ exports }) {
  if (!exports?.length) return null;

  return (
    <div className="export-links">
      {exports.map((item) => (
        <a key={item.name} href={exportUrl(item.name)} className="export-link" download>
          ⬇ {item.name}
        </a>
      ))}
    </div>
  );
}
