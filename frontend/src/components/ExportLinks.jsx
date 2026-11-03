import { useState } from "react";
import { FileDown } from "lucide-react";
import { downloadExport } from "../api";

export default function ExportLinks({ exports }) {
  const [error, setError] = useState("");
  if (!exports?.length) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {exports.map((item) => (
        <button
          type="button"
          key={item.name}
          onClick={() => downloadExport(item.name).then(() => setError(""), (err) => setError(err.message))}
          className="flex items-center gap-2.5 rounded-lg border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 px-3 py-2 text-sm hover:border-stone-300 dark:hover:border-stone-700 hover:bg-stone-50 dark:hover:bg-stone-800"
        >
          <FileDown className="size-4 text-accent-600 dark:text-accent-400" />
          <span className="font-medium text-stone-800 dark:text-stone-200">{item.name}</span>
          <span className="text-xs text-stone-500 dark:text-stone-400">Descarregar</span>
        </button>
      ))}
      {error && <p className="w-full text-xs text-red-700 dark:text-red-300">{error}</p>}
    </div>
  );
}
