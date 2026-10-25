"use client";
import { ReactNode, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

export default function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const pressedBackdrop = useRef(false);
  const id = useId();
  useEffect(() => {
    if (!open || !ref.current) return;
    pressedBackdrop.current = false;
    const element = ref.current;
    const previous = document.body.style.overflow;
    const previousFocus = document.activeElement;
    element.showModal(); document.body.style.overflow = "hidden";
    return () => {
      element.close(); document.body.style.overflow = previous;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, [open]);
  if (!open) return null;
  function isBackdrop(event: { target: EventTarget; currentTarget: HTMLDialogElement; clientX: number; clientY: number }) {
    if (event.target !== event.currentTarget) return false;
    const bounds = event.currentTarget.getBoundingClientRect();
    return event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom;
  }
  return createPortal(<dialog ref={ref} className="planner-modal" aria-labelledby={id} onCancel={event => { event.preventDefault(); onClose(); }} onClose={onClose}
    onPointerDown={event => { pressedBackdrop.current = isBackdrop(event); }}
    onPointerCancel={() => { pressedBackdrop.current = false; }}
    onClick={event => {
      const close = pressedBackdrop.current && isBackdrop(event);
      pressedBackdrop.current = false;
      if (close) onClose();
    }}>
    <div className="modal-shell"><header className="modal-header"><div><small>YOUR HONEYMOON · JOURNEY PLANNING</small><h2 id={id}>{title}</h2></div><button type="button" aria-label="Close journey dialog" onClick={onClose}>×</button></header><div className="modal-body">{children}</div></div>
  </dialog>, document.body);
}
