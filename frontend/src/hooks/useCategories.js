import { useAppStore } from '../store/appStore'

export const useCategories = () => {
  const categories = useAppStore((s) => s.categories)

  const findCategory = (id) => {
    return categories.find((c) => c.id === id) ?? null
  }

  const findSubcategory = (categoryId, subcategoryId) => {
    const category = findCategory(categoryId)
    if (!category) return null
    return category.subcategories?.find((s) => s.id === subcategoryId) ?? null
  }

  const findSubcategoryById = (subcategoryId) => {
    for (const cat of categories) {
      const sub = cat.subcategories?.find((s) => s.id === subcategoryId)
      if (sub) return { ...sub, category }
    }
    return null
  }

  const getSubcategories = (categoryId) => {
    const category = findCategory(categoryId)
    return category?.subcategories ?? []
  }

  return {
    categories,
    findCategory,
    findSubcategory,
    findSubcategoryById,
    getSubcategories,
  }
}
