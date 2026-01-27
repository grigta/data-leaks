import type { PageLoad } from './$types';
import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import { z } from 'zod';

const loginSchema = z.object({
	access_code: z
		.string()
		.min(15, 'Код доступа должен быть в формате XXX-XXX-XXX-XXX')
		.max(15, 'Код доступа должен быть в формате XXX-XXX-XXX-XXX')
		.regex(/^\d{3}-\d{3}-\d{3}-\d{3}$/, 'Неверный формат кода доступа')
});

export const load: PageLoad = async () => {
	// При CSR создаем форму на клиенте
	const form = await superValidate(null, zod(loginSchema), { id: 'login' });
	return { form };
};