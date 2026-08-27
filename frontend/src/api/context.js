import service from './index'

export const getContext = () => service.get('/api/context')
export const saveContext = (body) => service.put('/api/context', { body })
