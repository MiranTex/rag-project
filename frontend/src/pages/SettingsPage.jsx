import { useEffect, useState } from "react";
import { Loader2, RotateCcw, Save } from "lucide-react";
import { getSettings, resetSetting, saveSettings } from "../api";
import PageShell from "../components/PageShell";

const WEIGHT_FACTORS = [
  { key: "vector", label: "Significado" },
  { key: "lexical", label: "Texto" },
  { key: "keyword", label: "Palavras-chave" },
  { key: "position", label: "Posição" },
  { key: "density", label: "Densidade" },
];

const inputClass =
  "w-full rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-900 px-3 py-1.5 text-sm outline-none focus:border-stone-500";

// Os pesos chegam como texto JSON; no formulário editam-se como um número por fator.
function toDraft(setting) {
  if (setting.kind !== "weights") return setting.value;
  try {
    const parsed = JSON.parse(setting.value);
    return Object.fromEntries(WEIGHT_FACTORS.map(({ key }) => [key, parsed[key] ?? 0]));
  } catch {
    return Object.fromEntries(WEIGHT_FACTORS.map(({ key }) => [key, 0]));
  }
}

function sameValue(setting, draft) {
  if (setting.kind === "weights") return JSON.stringify(toDraft(setting)) === JSON.stringify(draft);
  return setting.value === draft;
}

function describeDefault(setting) {
  if (setting.kind === "bool") return setting.default ? "ligado" : "desligado";
  if (setting.kind === "weights") {
    try {
      const parsed = JSON.parse(setting.default);
      return WEIGHT_FACTORS.filter(({ key }) => parsed[key])
        .map(({ key, label }) => `${label} ${parsed[key]}`)
        .join(", ");
    } catch {
      return setting.default;
    }
  }
  return String(setting.default);
}

function Field({ setting, value, onChange, disabled }) {
  const id = `setting-${setting.key}`;
  switch (setting.kind) {
    case "bool":
      return (
        <input id={id} type="checkbox" checked={!!value} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      );
    case "choice":
      return (
        <select id={id} className={inputClass} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
          {setting.choices.map((choice) => (
            <option key={choice} value={choice}>
              {choice}
            </option>
          ))}
        </select>
      );
    case "textarea":
      return (
        <textarea
          id={id}
          className={inputClass}
          rows={3}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case "int":
    case "float":
      return (
        <input
          id={id}
          className={`${inputClass} max-w-32`}
          type="number"
          step={setting.kind === "int" ? 1 : 0.01}
          min={setting.minimum ?? undefined}
          max={setting.maximum ?? undefined}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        />
      );
    case "weights":
      return (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {WEIGHT_FACTORS.map(({ key, label }) => (
            <label key={key} className="text-xs text-stone-500 dark:text-stone-400">
              {label}
              <input
                className={`${inputClass} mt-1`}
                type="number"
                step={0.05}
                min={0}
                value={value[key]}
                disabled={disabled}
                onChange={(e) => onChange({ ...value, [key]: e.target.value === "" ? 0 : Number(e.target.value) })}
              />
            </label>
          ))}
        </div>
      );
    default:
      return (
        <input id={id} className={inputClass} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
      );
  }
}

export default function SettingsPage({ onOpenSidebar, onSaved }) {
  const [settings, setSettings] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function load(list) {
    setSettings(list);
    setDrafts(Object.fromEntries(list.map((s) => [s.key, toDraft(s)])));
  }

  useEffect(() => {
    getSettings()
      .then(load)
      .catch((err) => setError(err.message));
  }, []);

  const changed = settings ? settings.filter((s) => !sameValue(s, drafts[s.key])) : [];

  async function run(action, message) {
    setSaving(true);
    setError("");
    try {
      load(await action());
      onSaved(message);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const groups = settings ? [...new Set(settings.map((s) => s.group))] : [];

  return (
    <PageShell
      title="Configurações"
      description="Valem para toda a aplicação e aplicam-se em poucos segundos, sem reiniciar. Os valores por defeito vêm do ficheiro .env."
      onOpenSidebar={onOpenSidebar}
      actions={
        settings && (
          <button
            type="button"
            disabled={saving || changed.length === 0}
            onClick={() =>
              run(
                () => saveSettings(Object.fromEntries(changed.map((s) => [s.key, drafts[s.key]]))),
                "Configurações guardadas.",
              )
            }
            className="flex items-center gap-2 rounded-lg bg-accent-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-600 disabled:bg-stone-300 dark:disabled:bg-stone-700"
          >
            {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
            Guardar{changed.length > 0 && ` (${changed.length})`}
          </button>
        )
      }
    >
      {error && <p className="mb-4 text-sm text-red-700 dark:text-red-300">{error}</p>}
      {!settings && !error && <Loader2 className="size-5 animate-spin text-stone-400" />}
      {groups.map((group) => (
        <section key={group} className="mb-8">
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-stone-500 dark:text-stone-400">{group}</h2>
          <div className="divide-y divide-stone-200 rounded-xl border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
            {settings
              .filter((s) => s.group === group)
              .map((setting) => (
                <div key={setting.key} className="space-y-2 p-4">
                  <div className={setting.kind === "bool" ? "flex items-start gap-3" : "space-y-2"}>
                    {setting.kind === "bool" && (
                      <div className="pt-0.5">
                        <Field
                          setting={setting}
                          value={drafts[setting.key]}
                          disabled={saving}
                          onChange={(value) => setDrafts({ ...drafts, [setting.key]: value })}
                        />
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <label htmlFor={`setting-${setting.key}`} className="text-sm font-medium text-stone-800 dark:text-stone-200">
                        {setting.label}
                      </label>
                      <p className="text-sm text-stone-500 dark:text-stone-400">{setting.help}</p>
                    </div>
                  </div>
                  {setting.kind !== "bool" && (
                    <Field
                      setting={setting}
                      value={drafts[setting.key]}
                      disabled={saving}
                      onChange={(value) => setDrafts({ ...drafts, [setting.key]: value })}
                    />
                  )}
                  {setting.overridden && (
                    <p className="flex flex-wrap items-center gap-2 text-xs text-stone-500 dark:text-stone-400">
                      Alterado na aplicação. Valor do .env: {describeDefault(setting)}
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() => run(() => resetSetting(setting.key), `${setting.label}: valor do .env reposto.`)}
                        className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-accent-600 hover:bg-accent-50 dark:text-accent-400 dark:hover:bg-accent-500/15"
                      >
                        <RotateCcw className="size-3" />
                        Repor
                      </button>
                    </p>
                  )}
                </div>
              ))}
          </div>
        </section>
      ))}
    </PageShell>
  );
}
