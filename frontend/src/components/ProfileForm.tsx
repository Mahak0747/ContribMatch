import { ArrowRight, LoaderCircle } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { fieldErrors, toApiError, type ApiError } from '../api/client'
import { saveProfile } from '../api/endpoints'
import { EMPTY_PROFILE } from '../lib/profile'
import { DOMAIN_SUGGESTIONS, LANGUAGE_SUGGESTIONS, LEARNING_SUGGESTIONS, SKILL_SUGGESTIONS } from '../lib/suggestions'
import type { ExperienceLevel, ProfileInput, SavedProfile } from '../types/api'
import { SkillSelector } from './SkillSelector'

const LEVELS: { value: ExperienceLevel; title: string; text: string }[] = [
  { value: 'beginner', title: 'Beginner', text: 'New to contributing. Prefers well-scoped, labelled starter issues.' },
  { value: 'intermediate', title: 'Intermediate', text: 'Comfortable with a codebase. Open to "help wanted" work.' },
  { value: 'advanced', title: 'Advanced', text: 'Experienced. Happy with larger or less-defined issues.' },
]

interface Props {
  initial?: ProfileInput
  onSaved: (p: SavedProfile) => void
}

export function ProfileForm({ initial = EMPTY_PROFILE, onSaved }: Props) {
  const [values, setValues] = useState<ProfileInput>(initial)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [apiError, setApiError] = useState<ApiError | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})

  const set = <K extends keyof ProfileInput>(k: K, v: ProfileInput[K]) => setValues((p) => ({ ...p, [k]: v }))
  const isEmpty = !(values.skills.length || values.preferred_languages.length || values.domains.length || values.learning_interests.length)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setApiError(null)
    setFields({})
    if (isEmpty) {
      setFormError('Add at least one skill, language, domain or learning interest so there is something to match on.')
      return
    }
    setFormError(null)
    setSubmitting(true)
    try {
      onSaved(await saveProfile(values))
    } catch (err) {
      const e2 = toApiError(err)
      setApiError(e2)
      setFields(fieldErrors(e2))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-8" aria-label="Developer profile">
      <SkillSelector label="Technical skills" hint="Tools, frameworks and languages you already use." value={values.skills}
        onChange={(v) => set('skills', v)} suggestions={SKILL_SUGGESTIONS} placeholder="e.g. Python, React, Docker" error={fields.skills} />

      <SkillSelector label="Preferred programming languages"
        hint="Used to search GitHub. The first two languages you list are searched." value={values.preferred_languages}
        onChange={(v) => set('preferred_languages', v)} suggestions={LANGUAGE_SUGGESTIONS} placeholder="e.g. Python" error={fields.preferred_languages} />

      <SkillSelector label="Preferred domains"
        hint="The first domain you list is used as a search keyword, so put your most important one first."
        value={values.domains} onChange={(v) => set('domains', v)} suggestions={DOMAIN_SUGGESTIONS} placeholder="e.g. Machine learning" error={fields.domains} />

      <SkillSelector label="Things you want to learn"
        hint="Issues that mention these are highlighted as learning opportunities." value={values.learning_interests}
        onChange={(v) => set('learning_interests', v)} suggestions={LEARNING_SUGGESTIONS} placeholder="e.g. Rust" error={fields.learning_interests} />

      <fieldset>
        <legend className="mb-1 text-sm font-medium text-slate-100">Experience level</legend>
        <p className="mb-2 text-xs text-slate-500">Chooses which issue labels are searched and how difficulty is judged.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          {LEVELS.map((l) => {
            const active = values.experience_level === l.value
            return (
              <label key={l.value}
                className={`cursor-pointer rounded-lg border p-3 transition-colors focus-within:outline-2 focus-within:outline-violet-400 ${active ? 'border-violet-400/60 bg-violet-500/10' : 'border-white/10 bg-white/[0.03] hover:bg-white/5'}`}>
                <input type="radio" name="experience_level" value={l.value} checked={active} className="sr-only"
                  onChange={() => set('experience_level', l.value)} />
                <span className="block text-sm font-medium text-slate-100">{l.title}</span>
                <span className="mt-1 block text-xs text-slate-400">{l.text}</span>
              </label>
            )
          })}
        </div>
      </fieldset>

      {formError && <p role="alert" className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">{formError}</p>}
      {apiError && Object.keys(fields).length === 0 && (
        <p role="alert" className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{apiError.message}</p>
      )}

      <div className="flex items-center gap-4">
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting
            ? <><LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> Saving…</>
            : <>Save profile &amp; find issues <ArrowRight className="h-4 w-4" aria-hidden /></>}
        </button>
      </div>
    </form>
  )
}
