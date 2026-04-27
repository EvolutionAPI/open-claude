import { expect, test } from '@playwright/test'

test('setup and login flow reaches the dashboard', async ({ page, browser }) => {
  const adminPassword = 'Valid!1234'

  await page.goto('/')
  await page.locator('input[autocomplete="username"], input[autocomplete="organization"]').first().waitFor({ state: 'visible' })
  const organizationField = page.locator('input[autocomplete="organization"]')
  if (await organizationField.count() > 0) {
    await page.locator('input[autocomplete="name"]').first().fill('Evo Nexus')
    await organizationField.fill('EvoNexus')
    await page.getByRole('button', { name: /continue/i }).click()
  }

  await page.locator('input[autocomplete="username"]').fill('admin')
  await page.locator('input[autocomplete="email"]').fill('admin@example.com')
  await page.locator('input[autocomplete="name"]').fill('Admin User')

  const newPasswordInputs = page.locator('input[autocomplete="new-password"]')
  await newPasswordInputs.nth(0).fill(adminPassword)
  await newPasswordInputs.nth(1).fill(adminPassword)
  await page.getByRole('button', { name: /create account/i }).click()
  await expect(page).toHaveURL(/\/providers$/)

  const loginContext = await browser.newContext()
  const loginPage = await loginContext.newPage()

  await loginPage.goto('/login')
  await loginPage.locator('input[autocomplete="username"]').fill('admin')
  await loginPage.locator('input[autocomplete="current-password"]').fill(adminPassword)
  await loginPage.getByRole('button', { name: /sign in/i }).click()
  await expect(loginPage).toHaveURL(/\/providers$/)

  await loginPage.goto('/agents')
  await expect(loginPage).toHaveURL(/\/agents/)
  await expect(loginPage.locator('body')).toContainText(/Agents/i)
})
