"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiRequest } from "@/lib/api";
import { getActiveShopId } from "@/lib/shop-context";
import { Send, Bot, Sparkles, Loader2 } from "lucide-react";

type Message = {
  role: "user" | "assistant";
  content: string;
};

const WELCOME =
  "Welcome to DUKAANTRA Intelligence. I can analyse your inventory, orders, revenue and business performance using your shop's recorded data. What would you like to understand today?";

export default function AIAssistant() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: WELCOME },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function sendMessage() {
    const message = input.trim();
    if (!message || loading) return;

    const history = messages
      .filter((item) => item.content !== WELCOME)
      .slice(-8);

    setMessages((current) => [
      ...current,
      { role: "user", content: message },
    ]);
    setInput("");
    setError("");
    setLoading(true);

    try {
      const result = await apiRequest<{
        success: boolean;
        reply: string;
      }>(`/api/v1/shops/${getActiveShopId()}/ai/chat`, {
        method: "POST",
        body: JSON.stringify({ message, history }),
      });

      setMessages((current) => [
        ...current,
        { role: "assistant", content: result.reply },
      ]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to complete the request. Please try again."
      );
      setMessages((current) => current.slice(0, -1));
      setInput(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ai-page">
      <div className="ai-heading">
        <div>
          <span className="eyebrow">INTELLIGENCE / AI WORKSPACE</span>
          <h1>DUKAANTRA AI</h1>
          <p>Your business intelligence assistant, powered by Gemini.</p>
        </div>
        <span className="eyebrow">
          GEMINI-POWERED · AVAILABILITY DEPENDS ON CONFIGURATION
        </span>
      </div>

      <section className="ai-chat-panel">
        <header className="ai-chat-top">
          <div className="ai-avatar"><Sparkles size={19} /></div>
          <div>
            <strong>DUKAANTRA Intelligence</strong>
            <span>Shop-aware business assistant</span>
          </div>
        </header>

        <div className="ai-messages">
          {messages.map((message, index) => (
            <article className={`ai-message ${message.role}`} key={index}>
              {message.role === "assistant" && (
                <span className="ai-message-icon"><Bot size={17} /></span>
              )}
              <div className={message.role === "assistant" ? "ai-markdown" : "ai-user-text"}>
                {message.role === "assistant" ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {message.content}
                  </ReactMarkdown>
                ) : message.content}
              </div>
            </article>
          ))}

          {loading && (
            <div className="ai-message assistant">
              <span className="ai-message-icon"><Bot size={17} /></span>
              <div className="ai-thinking">
                <Loader2 size={15} className="animate-spin" />
                Analysing your business data...
              </div>
            </div>
          )}
        </div>

        {error && <div className="ai-error">{error}</div>}

        <div className="ai-composer">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void sendMessage();
              }
            }}
            placeholder="Ask about your inventory, sales or business..."
            rows={2}
            maxLength={2000}
            disabled={loading}
          />
          <button
            onClick={() => void sendMessage()}
            disabled={loading || !input.trim()}
          >
            {loading ? <Loader2 size={17} className="animate-spin" /> : <Send size={17} />}
            Send
          </button>
        </div>

        <p className="ai-disclaimer">
          Insights are based on available shop records. Verify important business decisions.
        </p>
      </section>
    </div>
  );
}
