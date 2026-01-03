import { Sparkles, Plus, Search, FileText } from "lucide-react";

const themes = [
  {
    id: "A",
    title: "Building intelligent agents",
    description: "physical testbed for \"learning reflexes,\" microcontroller for reflexes,",
    highlighted: true,
  },
  {
    id: "B",
    title: 'The "learn-while-acting" loop',
    description: "Knowledge) and Vitalik's memory directly inform our approach",
    highlighted: false,
  },
  {
    id: "C",
    title: "Impact of technological shifts",
    description: "boom, and the early internet; lowering publishing costs shows a pattern echoed in today's inf",
    highlighted: true,
  },
  {
    id: "D",
    title: "Company as product",
    description: "Tobi refactoring software, and the internal tool that became ext development philosophy.",
    highlighted: true,
  },
  {
    id: "E",
    title: "Identity and change",
    description: "The S defining the core, unchanging",
    highlighted: true,
  },
];

const ideas = [
  {
    id: "A",
    title: "AI for physical action",
    description: "The Q embodied agents, connecting",
    highlighted: true,
  },
  {
    id: "B",
    title: "Speed as a prerequisite for i",
    description: "underscores that for learning as processing it.",
    highlighted: true,
  },
  {
    id: "C",
    title: "Applying historical patterns",
    description: "(agile, value-aligned",
    highlighted: false,
  },
];

export function RightPanel() {
  return (
    <aside className="w-72 h-screen bg-card border-l border-border/50 flex flex-col overflow-hidden">
      {/* Tabs */}
      <div className="h-12 border-b border-border/50 flex items-center px-3 gap-2">
        <button className="flex items-center gap-1.5 px-2.5 py-1 bg-accent rounded-full">
          <Sparkles className="w-3.5 h-3.5 text-accent-amber" />
          <span className="text-xs font-medium text-foreground">Weekly distill</span>
        </button>
        <button className="p-1.5 hover:bg-accent rounded-lg transition-colors">
          <Plus className="w-3.5 h-3.5 text-muted-foreground" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto scrollbar-hide">
        {/* Weekly Distill Header */}
        <div className="p-3 border-b border-border/50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
              <FileText className="w-4 h-4 text-muted-foreground" />
            </div>
            <div>
              <h2 className="font-semibold text-sm text-foreground">Weekly Distill</h2>
              <p className="text-xxs text-muted-foreground">Create a distillation of you</p>
            </div>
          </div>
          
          <button className="mt-3 w-full flex items-center gap-1.5 px-3 py-2 border border-border rounded-lg text-xs text-muted-foreground hover:bg-accent transition-colors">
            <Search className="w-3.5 h-3.5" />
            <span>Search recent</span>
          </button>
        </div>

        {/* Artifact */}
        <div className="p-3 border-b border-border/50">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <FileText className="w-3.5 h-3.5" />
            <span>Artifact</span>
          </div>
        </div>

        {/* This Week's Distill */}
        <div className="p-3 border-b border-border/50">
          <h3 className="font-semibold text-sm text-foreground mb-2">This week's distill</h3>
          <p className="text-xs text-muted-foreground leading-relaxed">
            This week kicked off with a conversation emphasizing a polished "hero" feel—paired with explorations around agentic design, foundational principles of learning from younger cousins and 3D printing offers a counterbalance to the deeper...
          </p>
        </div>

        {/* Themes */}
        <div className="p-3 border-b border-border/50">
          <h3 className="font-semibold text-sm text-foreground mb-3">Themes</h3>
          <div className="space-y-3">
            {themes.map((theme) => (
              <div key={theme.id} className="animate-slide-in-left">
                <div className="flex gap-1.5">
                  <span className="text-xxs text-muted-foreground font-medium">{theme.id}.</span>
                  <div className="flex-1">
                    <p className="text-xs font-medium text-foreground leading-relaxed">
                      {theme.title}
                      {" — "}
                      <span className={theme.highlighted ? "highlight-text" : "text-muted-foreground"}>
                        {theme.description}
                      </span>
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Ideas and Connections */}
        <div className="p-3">
          <h3 className="font-semibold text-sm text-foreground mb-3">Ideas and connections</h3>
          <div className="space-y-3">
            {ideas.map((idea) => (
              <div key={idea.id} className="animate-slide-in-left">
                <div className="flex gap-1.5">
                  <span className="text-xxs text-muted-foreground font-medium">{idea.id}.</span>
                  <div className="flex-1">
                    <p className="text-xs leading-relaxed">
                      <span className={idea.highlighted ? "highlight-text font-medium" : "font-medium text-foreground"}>
                        {idea.title}
                      </span>
                      {": "}
                      <span className="text-muted-foreground">{idea.description}</span>
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}
