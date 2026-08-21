"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A name you rename by double-clicking it, wherever it appears.
 * Enter saves, Escape cancels, clicking away saves too.
 */
export default function EditableName({ name, onRename, className = "" }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const input = useRef(null);

  useEffect(() => {
    if (!editing) setDraft(name);
  }, [name, editing]);

  useEffect(() => {
    if (editing && input.current) {
      input.current.focus();
      input.current.select();
    }
  }, [editing]);

  function save() {
    const value = draft.trim();
    setEditing(false);
    if (value && value !== name) onRename(value);
  }

  if (editing) {
    return (
      <input
        ref={input}
        className={`name-input ${className}`}
        type="text"
        maxLength={80}
        value={draft}
        onClick={(event) => event.stopPropagation()}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={save}
        onKeyDown={(event) => {
          event.stopPropagation();
          if (event.key === "Enter") save();
          if (event.key === "Escape") {
            setDraft(name);
            setEditing(false);
          }
        }}
      />
    );
  }

  return (
    <span
      className={`editable ${className}`}
      title="Double-click to rename"
      onDoubleClick={(event) => {
        event.stopPropagation();
        setEditing(true);
      }}
    >
      {name}
    </span>
  );
}
