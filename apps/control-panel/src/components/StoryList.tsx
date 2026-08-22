import type { BacklogResponse } from '../api/controlApi';

export function StoryList({ backlog }: { backlog: BacklogResponse | null }) {
  if (!backlog) return null;
  return (
    <section className="stories card" aria-labelledby="stories-title">
      <div className="section-heading">
        <div><p className="eyebrow">PLANO DA SOLUÇÃO</p><h2 id="stories-title">O que será criado</h2></div>
        <span className="pill">{backlog.stories.length} funcionalidades</span>
      </div>
      <p className="stories-goal">{backlog.product_goal}</p>
      <ol className="story-grid">
        {backlog.stories.map((story, index) => (
          <li key={story.story_id}>
            <span className="story-number">{index + 1}</span>
            <div><h3>{story.title}</h3><p>{story.narrative}</p>
              <details><summary>O que será verificado</summary><ul>{story.acceptance_criteria.map((criterion) => <li key={criterion.criterion_id}>{criterion.description}</li>)}</ul></details>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
