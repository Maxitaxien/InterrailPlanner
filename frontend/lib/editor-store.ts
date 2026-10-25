import { create } from "zustand";
type EditorState = { active: number; setActive: (active: number) => void };
export const useEditorStore = create<EditorState>(set => ({ active: 0, setActive: active => set({ active }) }));
