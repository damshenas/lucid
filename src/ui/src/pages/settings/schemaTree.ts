import type { SettingsSchema, SchemaField } from "../../types";

export interface FieldNode {
  key: string; // dotted key used to save, e.g. "execution.fixed_usd"
  field: SchemaField;
}

export interface GroupNode {
  fields: FieldNode[];
  groups: Record<string, GroupNode>;
}

export function emptyGroup(): GroupNode {
  return { fields: [], groups: {} };
}

/**
 * Turns the flat `{section: {field: meta}}` schema into a nested tree so the UI can
 * render each level as tabs (and nested tabs). Two nesting sources are unified:
 *  - a section name containing dots (e.g. active-strategy extra sections like
 *    "strategy.trend_follow") nests under its parent section ("strategy").
 *  - a field name containing dots (e.g. a nested Pydantic model like
 *    "trailing_stop.atr_multiplier" inside the "strategy" section) nests the same way.
 */
export function buildSchemaTree(schema: SettingsSchema): Record<string, GroupNode> {
  const roots: Record<string, GroupNode> = {};

  for (const [section, fields] of Object.entries(schema)) {
    const sectionParts = section.split(".");
    const rootName = sectionParts[0];
    roots[rootName] ??= emptyGroup();
    let node = roots[rootName];
    for (const part of sectionParts.slice(1)) {
      node.groups[part] ??= emptyGroup();
      node = node.groups[part];
    }

    for (const [field, meta] of Object.entries(fields)) {
      const fieldParts = field.split(".");
      let fnode = node;
      for (const part of fieldParts.slice(0, -1)) {
        fnode.groups[part] ??= emptyGroup();
        fnode = fnode.groups[part];
      }
      fnode.fields.push({ key: `${section}.${field}`, field: meta });
    }
  }

  return roots;
}

/**
 * Canonical top-level section order (mirrors LucidConfig in src/conf/schema.py).
 * Fixed so the tab bar doesn't reshuffle/flicker while the schema is still loading —
 * each tab just shows a loading placeholder until its section arrives.
 */
export const SETTINGS_SECTION_ORDER = [
  "execution",
  "strategy",
  "schedule",
  "git_sync",
  "price",
  "broker",
  "logger",
];

export function humanize(name: string): string {
  return name
    .split(/[_.]/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
