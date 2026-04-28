import { api } from './api'

export const getCategories = async () => {
  const { data } = await api.get('/api/categories')
  return data
}

export const createCategory = async (categoryData) => {
  const { data } = await api.post('/api/categories', categoryData)
  return data
}

export const updateCategory = async (id, categoryData) => {
  const { data } = await api.put(`/api/categories/${id}`, categoryData)
  return data
}

export const deleteCategory = async (id) => {
  const { data } = await api.delete(`/api/categories/${id}`)
  return data
}

export const createSubcategory = async (subcategoryData) => {
  const { data } = await api.post('/api/subcategories', subcategoryData)
  return data
}

export const updateSubcategory = async (id, subcategoryData) => {
  const { data } = await api.put(`/api/subcategories/${id}`, subcategoryData)
  return data
}

export const deleteSubcategory = async (id) => {
  const { data } = await api.delete(`/api/subcategories/${id}`)
  return data
}

/** Persist a new subcategory order for one category (one call per drag-drop). */
export const reorderSubcategories = async (categoryId, subcategoryIds) => {
  await api.put(`/api/categories/${categoryId}/subcategories/reorder`, {
    subcategory_ids: subcategoryIds,
  })
}
