"use client";

import { useRadar } from "@/lib/RadarContext";

export default function Toasts() {
  const { toasts } = useRadar();

  return (
    <div className="toasts">
      {toasts.map((toast) => (
        <div key={toast.id} className={toast.bad ? "toast bad" : "toast"}>
          {toast.message}
        </div>
      ))}
    </div>
  );
}
