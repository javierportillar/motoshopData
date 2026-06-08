"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useSendMessage } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";

interface Message {
  role: "user" | "assistant";
  content: string;
  tools_used?: string[];
}

function ThinkingDots() {
  return (
    <span className="inline-flex gap-0.5">
      <span className="animate-bounce">.</span>
      <span className="animate-bounce" style={{ animationDelay: "0.15s" }}>.</span>
      <span className="animate-bounce" style={{ animationDelay: "0.3s" }}>.</span>
    </span>
  );
}

const MAX_TURNS = 20;

export default function ChatPage(): JSX.Element {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string>("");
  const [turnCount, setTurnCount] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const sendMessage = useSendMessage(conversationId);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSend = async () => {
    if (!input.trim() || isLoading || turnCount >= MAX_TURNS) return;

    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setIsLoading(true);

    try {
      const resp = await sendMessage(userMsg);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: resp.text, tools_used: resp.tools_used },
      ]);
      setConversationId(resp.conversation_id);
      setTurnCount(resp.turn_count);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Error al procesar tu consulta. Intentá de nuevo." },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col" style={{ height: "calc(100vh - 80px)" }}>
      {/* Header */}
      <div className="flex items-center justify-between px-1 py-3">
        <h1 className="text-lg font-bold text-text-primary">Chat con MotoShop</h1>
        <span className="text-xs text-text-muted">
          Turno {turnCount}/{MAX_TURNS}
        </span>
      </div>

      {/* Help block */}
      <details className="mb-3 text-sm">
        <summary className="cursor-pointer text-text-secondary hover:text-text-primary">
          ¿Qué puedo preguntar?
        </summary>
        <div className="mt-2 space-y-1 rounded-lg bg-surface-alt p-3 text-xs text-text-muted">
          <p>• ¿Cómo van las ventas este mes vs el pasado?</p>
          <p>• ¿Qué productos están dormidos hace más de 60 días?</p>
          <p>• ¿Quién es la mejor vendedora?</p>
          <p>• ¿Hay alertas críticas hoy?</p>
          <p>• ¿Cómo está el forecast?</p>
          <p>• ¿Cuánto vale el inventario?</p>
        </div>
      </details>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-3 pb-2">
        {messages.length === 0 && (
          <p className="py-10 text-center text-sm text-text-muted">
            Preguntale al asistente sobre el negocio. Usa lenguaje natural.
          </p>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm ${
                msg.role === "user"
                  ? "bg-primary text-primary-fg"
                  : "bg-surface-alt text-text-secondary border border-border"
              }`}
            >
              <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
              {msg.tools_used && msg.tools_used.length > 0 && (
                <p className="mt-1.5 text-xs opacity-60">
                  Tools: {msg.tools_used.join(", ")}
                </p>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="rounded-xl bg-surface-alt border border-border px-4 py-2.5 text-sm text-text-muted">
              Pensando<ThinkingDots />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border pt-3 pb-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={turnCount >= MAX_TURNS ? "Límite de turnos alcanzado" : "Escribí tu pregunta..."}
            disabled={isLoading || turnCount >= MAX_TURNS}
            className="flex-1 rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
            maxLength={500}
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim() || turnCount >= MAX_TURNS}
            className="rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-fg hover:bg-primary-light disabled:opacity-40 transition-colors"
          >
            Enviar
          </button>
        </div>
        {turnCount >= MAX_TURNS && (
          <p className="mt-2 text-xs text-text-muted text-center">
            Iniciá una nueva conversación (refrescá la página).
          </p>
        )}
      </div>
    </div>
  );
}
