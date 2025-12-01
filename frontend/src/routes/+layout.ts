import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ data }) => {
	// Передаем все данные из серверного layout
	return { ...data };
};
