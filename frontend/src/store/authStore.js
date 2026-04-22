import { create } from 'zustand'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
)

export { supabase }

export const useAuthStore = create((set, get) => ({
  user: null,
  session: null,
  loading: true,

  initialize: () => {
    // onAuthStateChange fires immediately with INITIAL_SESSION, then on every change.
    // Using it as the sole source of truth avoids race conditions with getSession().
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      set({
        session,
        user: session?.user ?? null,
        loading: false,
      })
    })

    // Return cleanup so StrictMode's double-invoke unsubscribes the first listener
    // before the second one is registered — preventing duplicate listeners.
    return () => subscription.unsubscribe()
  },

  signIn: async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
    set({ session: data.session, user: data.user })
    return data
  },

  signOut: async () => {
    await supabase.auth.signOut()
    set({ session: null, user: null })
  },

  getToken: () => {
    return get().session?.access_token ?? null
  },
}))
