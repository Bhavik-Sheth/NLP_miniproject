"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui";

type Session = {
  session_id: string;
  started_at: string;
  turns: Array<{ role: "user" | "agent"; text: string; state: string; created_at: string }>;
};

export default function ConversationHistory({ refreshKey }: { refreshKey: number }) {
  const [sessions, setSessions] = useState<Session[]>([]);

  useEffect(() => {
    void api.conversations().then((r) => setSessions(r.sessions)).catch(() => undefined);
  }, [refreshKey]);

  return (
    <Card title="Previous conversations">
      {sessions.length === 0 ? (
        <p className="text-xs text-zinc-500">Your verified voice and chat conversations will appear here.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {sessions.map((session) => (
            <details key={session.session_id} className="rounded-lg border border-white/10 bg-black/25 px-2.5 py-2">
              <summary className="cursor-pointer list-none text-xs text-zinc-300">
                <span className="font-mono text-[10px] text-zinc-500">{new Date(session.started_at).toLocaleString()}</span>
                <span className="ml-2">{session.turns.length} messages</span>
              </summary>
              <div className="mt-2 flex flex-col gap-1.5 border-t border-white/10 pt-2">
                {session.turns.map((turn, index) => (
                  <p key={`${turn.created_at}-${index}`} className={`text-xs leading-relaxed ${turn.role === "user" ? "text-zinc-300" : "text-sky-100"}`}>
                    <span className="mr-1 font-mono text-[10px] text-zinc-500">{turn.role === "user" ? "You" : "Vesper"}:</span>
                    {turn.text}
                  </p>
                ))}
              </div>
            </details>
          ))}
        </div>
      )}
    </Card>
  );
}
