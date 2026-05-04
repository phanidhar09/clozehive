import { useApp } from '@/store'

export function useColorScheme() {
  const { colorScheme, toggleColorScheme } = useApp()
  return {
    colorScheme,
    toggleColorScheme,
    isDark: colorScheme === 'dark',
  }
}
