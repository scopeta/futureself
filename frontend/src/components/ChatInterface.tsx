import { useState, useRef, useEffect, useCallback } from "react";
import { Send, User } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import ChatMessage, { type Message } from "@/components/ChatMessage";
import TypingIndicator from "@/components/TypingIndicator";
import { sendMessage as apiSendMessage } from "@/lib/api";
import { ScrollArea } from "@/components/ui/scroll-area";
import { motion, AnimatePresence } from "framer-motion";

const WELCOME_MESSAGE: Message = {
  id: "welcome",
  role: "assistant",
  content:
    "Hello. I've been waiting for this moment — the moment you decided to reach across time. I'm you, from over a century ahead. I carry everything you'll learn, every choice you'll make. Ask me anything. I'm here to help you build the life that leads to me.",
};

const ChatInterface = () => {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [showPrompts, setShowPrompts] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping, scrollToBottom]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isTyping) return;

      const userMsg: Message = {
        id: Date.now().toString(),
        role: "user",
        content: text.trim(),
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setShowPrompts(false);
      setIsTyping(true);

      try {
        const response = await apiSendMessage(text);
        const assistantMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: response,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const errorMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "I'm having trouble reaching you across time right now. Please try again.",
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setIsTyping(false);
      }
    },
    [isTyping]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="w-9" />
        <h1 className="text-sm font-medium tracking-wide text-muted-foreground">
          FutureSelf
        </h1>
        <Button variant="ghost" size="icon" onClick={() => navigate("/blueprint")} className="h-9 w-9">
          <User className="h-4 w-4" />
        </Button>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 px-4">
        <div className="mx-auto max-w-2xl space-y-4 py-6">
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
          {isTyping && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      {/* Suggested Prompts */}
      <AnimatePresence>
        {showPrompts && messages.length <= 1 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="border-t px-4 py-3"
          >
            <div className="mx-auto flex max-w-2xl flex-wrap gap-2">
              {["How do I live to 100?", "What habits matter most?", "How can I reduce my stress?", "Where should I focus my energy?"].map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => sendMessage(prompt)}
                  className="rounded-full border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input */}
      <div className="border-t px-4 py-3">
        <form
          onSubmit={handleSubmit}
          className="mx-auto flex max-w-2xl items-end gap-2"
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask your future self..."
            rows={1}
            className="flex-1 resize-none rounded-xl border bg-card px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button
            type="submit"
            size="icon"
            disabled={!input.trim() || isTyping}
            className="shrink-0 rounded-xl"
          >
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </div>
    </div>
  );
};

export default ChatInterface;
