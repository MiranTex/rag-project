import { FileDown } from "lucide-react";
import { exportUrl } from "../api";

export default function ExportLinks({ exports }) {
  if (!exports?.length) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {exports.map((item) => (
        <a
          key={item.name}
          href={exportUrl(item.name)}
          download
          className="flex items-center gap-2.5 rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm hover:border-stone-300 hover:bg-stone-50"
        >
          <FileDown className="size-4 text-accent-600" />
          <span className="font-medium text-stone-800">{item.name}</span>
          <span className="text-xs text-stone-500">Descarregar</span>
        </a>
      ))}
    </div>
  );
}
