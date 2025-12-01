import type { PageLoad } from './$types';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import { z } from 'zod';

const registerSchema = z.object({
	// Регистрация не требует полей ввода, но создадим пустую схему для совместимости
});

export const load: PageLoad = async () => {
	// При CSR создаем форму на клиенте
	const form = await superValidate(null, zod(registerSchema), { id: 'register' });
	return { form };
};