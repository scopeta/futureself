const responses: Record<string, string[]> = {
  default: [
    "I remember this moment — the one where you started asking the right questions. That curiosity? It's what carried us through our second century.",
    "You know what I wish I could tell every version of myself? That the small, consistent choices matter infinitely more than the dramatic ones. A daily walk. A moment of stillness. A real conversation with someone you love.",
    "From where I stand, I can see the threads of your life weaving together in ways you can't yet imagine. Trust the process. Your body and mind are more resilient than you think.",
    "I've learned something about time that you haven't yet: it's not about adding years to your life. It's about adding life to your years. Every single one of them.",
    "The fact that you're here, thinking about your future health — that's not a small thing. That's the beginning of everything.",
  ],
  physical: [
    "Your body is extraordinary. In my time, we understand that movement isn't punishment — it's celebration. Find ways to move that make you feel alive, not depleted.",
    "Sleep became my superpower. I know it feels like a luxury now, but I promise you — prioritizing 7-8 hours of quality sleep will compound in ways you can't imagine.",
    "Here's something we learned: your gut microbiome is like a garden. Feed it diversity — different plants, fermented foods, fiber. The garden you plant now, I'm still harvesting.",
  ],
  mental: [
    "Your mind is the most powerful longevity tool you have. The stress you're carrying right now? It's aging you faster than anything else. Learning to let go isn't weakness — it's wisdom.",
    "I meditate every morning. I know — you're skeptical. But those quiet minutes became the foundation of my mental clarity for over a century.",
    "Curiosity kept me young. Never stop learning, never stop being amazed. The moment you think you know everything is the moment you start aging.",
  ],
  financial: [
    "Financial health is longevity health. The stress of money worries accelerates aging more than most people realize. Start where you are. Automate what you can. Future you will thank you.",
    "I learned to invest in experiences and relationships over things. The compound interest that matters most isn't in your bank account — it's in your connections.",
  ],
  social: [
    "Here's a secret from the future: loneliness is as dangerous as smoking. Your relationships are literally keeping you alive. Nurture them fiercely.",
    "The friends you invest in now? Some of them walked with me for decades. Don't take a single conversation for granted.",
  ],
  environmental: [
    "Your environment shapes you more than you know. The air you breathe, the water you drink, the light you absorb — these aren't background details. They're the medium of your life.",
    "I moved somewhere with clean air and access to nature. It wasn't easy, but it was one of the best decisions I ever made for our longevity.",
  ],
};

function detectCategory(message: string): string {
  const lower = message.toLowerCase();
  if (/exercise|workout|sleep|body|physical|eat|diet|food|nutrition|weight/.test(lower)) return "physical";
  if (/stress|mind|mental|meditat|anxiety|brain|think|focus|depress/.test(lower)) return "mental";
  if (/money|financ|invest|retire|save|income|budget/.test(lower)) return "financial";
  if (/friend|social|relation|family|love|lonely|communit/.test(lower)) return "social";
  if (/environment|nature|air|water|climate|pollution|outdoors/.test(lower)) return "environmental";
  return "default";
}

export function getMockResponse(userMessage: string): string {
  const category = detectCategory(userMessage);
  const pool = responses[category];
  return pool[Math.floor(Math.random() * pool.length)];
}

export const suggestedPrompts = [
  "What should I focus on today?",
  "How's my future looking?",
  "What's the most important health habit?",
  "Tell me about longevity",
  "How do I manage stress better?",
];
