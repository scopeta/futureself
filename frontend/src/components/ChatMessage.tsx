import ReactMarkdown from "react-markdown";
import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface ChatMessageProps {
  message: Message;
}

const ChatMessage = ({ message }: ChatMessageProps) => {
  const isAssistant = message.role === "assistant";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className={`flex gap-3 ${isAssistant ? "justify-start" : "justify-end"}`}
    >
      {isAssistant && (
        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent shadow-sm shadow-future-glow/20">
          <Sparkles className="h-4 w-4 text-primary" />
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isAssistant
            ? "bg-future-surface text-foreground shadow-sm shadow-future-glow/10"
            : "bg-primary text-primary-foreground"
        }`}
      >
        <div className="prose prose-sm prose-green max-w-none dark:prose-invert">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
      </div>
    </motion.div>
  );
};

export default ChatMessage;
