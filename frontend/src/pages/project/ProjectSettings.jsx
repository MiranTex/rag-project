import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Trash2, X } from "lucide-react";
import { research } from "../../api";
import { Button, Drawer, ErrorText, Field, IconButton, inputClass, uniqueKey, useConfirm } from "../../components/ui";

// Secções do caderno e estados das entradas. As chaves não mudam ao renomear, para as entradas continuarem
// ligadas à secção. Usado nas definições do projeto e na proposta de projeto a partir do chat.
export function StructureEditor({ sections, statuses, onChange, disabled = false }) {
  const [newSection, setNewSection] = useState("");

  function addSection(event) {
    event.preventDefault();
    const title = newSection.trim();
    if (!title) return;
    onChange({ sections: [...sections, { key: uniqueKey(title, sections), title, description: "" }], statuses });
    setNewSection("");
  }

  function move(index, delta) {
    const next = [...sections];
    const [moved] = next.splice(index, 1);
    next.splice(index + delta, 0, moved);
    onChange({ sections: next, statuses });
  }

  const setSection = (key, changes) => onChange({ sections: sections.map((s) => (s.key === key ? { ...s, ...changes } : s)), statuses });

  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-sm font-medium text-stone-700 dark:text-stone-300">Secções do caderno</p>
        {sections.length === 0 && <p className="mb-2 text-sm text-stone-500 dark:text-stone-400">Sem secções: as entradas ficam numa lista única.</p>}
        <ul className="space-y-2">
          {sections.map((section, index) => (
            <li key={section.key} className="rounded-lg border border-stone-200 p-2 dark:border-stone-800">
              <div className="flex items-center gap-1">
                <input
                  className={inputClass}
                  value={section.title}
                  disabled={disabled}
                  onChange={(e) => setSection(section.key, { title: e.target.value })}
                  aria-label={`Título da secção ${index + 1}`}
                />
                {!disabled && (
                  <>
                    <IconButton icon={ArrowUp} label="Subir" disabled={index === 0} onClick={() => move(index, -1)} />
                    <IconButton icon={ArrowDown} label="Descer" disabled={index === sections.length - 1} onClick={() => move(index, 1)} />
                    <IconButton
                      icon={X}
                      label={`Retirar a secção ${section.title}`}
                      onClick={() => onChange({ sections: sections.filter((s) => s.key !== section.key), statuses })}
                    />
                  </>
                )}
              </div>
              <input
                className={`${inputClass} mt-1 text-xs`}
                value={section.description || ""}
                disabled={disabled}
                placeholder="O que entra nesta secção (opcional; o assistente usa isto)"
                aria-label={`Descrição da secção ${section.title}`}
                onChange={(e) => setSection(section.key, { description: e.target.value })}
              />
            </li>
          ))}
        </ul>
        {!disabled && (
          <form onSubmit={addSection} className="mt-2 flex gap-2">
            <input className={inputClass} placeholder="Nova secção" aria-label="Nova secção" value={newSection} onChange={(e) => setNewSection(e.target.value)} />
            <Button type="submit" icon={Plus}>
              Secção
            </Button>
          </form>
        )}
      </div>
      <StatusesInput statuses={statuses} disabled={disabled} onChange={(next) => onChange({ sections, statuses: next })} />
    </div>
  );
}

// Estados escritos separados por vírgulas; só se aplicam ao sair do campo, para se poder escrever à vontade.
function StatusesInput({ statuses, onChange, disabled }) {
  const [text, setText] = useState(statuses.join(", "));
  useEffect(() => setText(statuses.join(", ")), [statuses.join("|")]);
  return (
    <Field label="Estados das entradas" hint="Do primeiro (em aberto) ao último (concluído), separados por vírgulas. Vazio: sem estados.">
      <input
        className={inputClass}
        disabled={disabled}
        placeholder="Ex.: proposto, em revisão, aprovado"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => onChange([...new Set(text.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean))])}
      />
    </Field>
  );
}

// Definições do projeto numa gaveta: dados, estrutura e (para o dono) apagar. Um só "Guardar" para tudo.
export default function ProjectSettings({ detail, onSaved, onDeleted, onClose }) {
  const confirm = useConfirm();
  const { project } = detail;
  const canEdit = detail.my_role !== "viewer";
  const isOwner = detail.my_role === "owner";
  const [draft, setDraft] = useState({
    title: project.title,
    question: project.question,
    description: project.description,
    work_type: project.work_type,
    structure: project.structure,
  });
  const [workTypes, setWorkTypes] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    research.workTypes().then(setWorkTypes).catch(() => {});
  }, []);

  const dirty =
    ["title", "question", "description", "work_type"].some((key) => draft[key] !== project[key]) ||
    JSON.stringify(draft.structure) !== JSON.stringify(project.structure);

  async function save() {
    setSaving(true);
    setError("");
    try {
      onSaved(await research.updateProject(project.project_id, { ...draft, structure: { ...draft.structure, sections: draft.structure.sections.map((s) => ({ ...s, title: s.title.trim() })) } }));
      onClose();
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  async function close() {
    if (dirty && !(await confirm({ title: "Sair sem guardar?", message: "As alterações às definições perdem-se.", confirmLabel: "Sair sem guardar" }))) return;
    onClose();
  }

  async function remove() {
    const ok = await confirm({
      title: "Apagar o projeto?",
      message: `"${project.title}" e tudo o que tem (caderno, conversas, comentários, matriz) deixam de existir para todos os membros. Os documentos da base não são apagados.`,
      confirmLabel: "Apagar projeto",
    });
    if (!ok) return;
    research.deleteProject(project.project_id).then(onDeleted, (err) => setError(err.message));
  }

  return (
    <Drawer
      title="Definições do projeto"
      onClose={close}
      footer={
        canEdit && (
          <>
            <Button variant="ghost" onClick={close}>
              Cancelar
            </Button>
            <Button variant="primary" busy={saving} disabled={!dirty || !draft.title.trim() || draft.structure.sections.some((s) => !s.title.trim())} onClick={save}>
              Guardar
            </Button>
          </>
        )
      }
    >
      <div className="space-y-8">
        <section className="space-y-3">
          <h3 className="text-sm font-semibold">Projeto</h3>
          <Field label="Título">
            <input className={inputClass} value={draft.title} disabled={!canEdit} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </Field>
          <Field label="Objetivo" hint="Orienta o assistente e o que for gerado no projeto.">
            <textarea className={inputClass} rows={2} value={draft.question} disabled={!canEdit} onChange={(e) => setDraft({ ...draft, question: e.target.value })} />
          </Field>
          <Field label="Descrição">
            <textarea
              className={inputClass}
              rows={3}
              placeholder="Âmbito, prazos, quem participa…"
              value={draft.description}
              disabled={!canEdit}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            />
          </Field>
          <Field label="Tipo de documento a escrever" hint="Usado no separador Escrita, para o esqueleto.">
            <select className={inputClass} value={draft.work_type} disabled={!canEdit} onChange={(e) => setDraft({ ...draft, work_type: e.target.value })}>
              <option value="">Nenhum</option>
              {workTypes.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
          </Field>
        </section>

        <section>
          <h3 className="mb-3 text-sm font-semibold">Estrutura</h3>
          <StructureEditor
            sections={draft.structure.sections}
            statuses={draft.structure.statuses}
            disabled={!canEdit}
            onChange={(structure) => setDraft({ ...draft, structure })}
          />
        </section>

        <ErrorText>{error}</ErrorText>

        {isOwner && (
          <section className="rounded-xl border border-red-200 p-4 dark:border-red-900/60">
            <h3 className="text-sm font-semibold text-red-700 dark:text-red-300">Zona de perigo</h3>
            <p className="mb-3 mt-1 text-sm text-stone-600 dark:text-stone-400">Apagar o projeto apaga-o para todos os membros. Não se pode desfazer.</p>
            <Button variant="danger-solid" icon={Trash2} onClick={remove}>
              Apagar projeto
            </Button>
          </section>
        )}
      </div>
    </Drawer>
  );
}
