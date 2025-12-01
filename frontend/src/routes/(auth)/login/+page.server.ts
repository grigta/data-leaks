import { superValidate } from 'sveltekit-superforms';
import { zod } from 'sveltekit-superforms/adapters';
import { fail } from '@sveltejs/kit';
import { z } from 'zod';
import type { PageServerLoad, Actions } from './$types';

const loginSchema = z.object({
	access_code: z
		.string()
		.min(15, 'Код доступа должен быть в формате XXX-XXX-XXX-XXX')
		.max(15, 'Код доступа должен быть в формате XXX-XXX-XXX-XXX')
		.regex(/^\d{3}-\d{3}-\d{3}-\d{3}$/, 'Неверный формат кода доступа')
});

export const load: PageServerLoad = async () => {
	const form = await superValidate(null, zod(loginSchema), { id: 'login' });
	return { form };
};

export const actions: Actions = {
	default: async ({ request }) => {
		const form = await superValidate(request, zod(loginSchema), { id: 'login' });

		if (!form.valid) {
			return fail(400, { form });
		}

		// Логика обрабатывается на клиенте через onUpdate
		return { form };
	}
};
