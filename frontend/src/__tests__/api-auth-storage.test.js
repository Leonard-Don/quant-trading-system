describe('api auth storage', () => {
  beforeEach(() => {
    jest.resetModules();
    window.localStorage.clear();
  });

  it('migrates legacy Quant Lab token keys to public research keys on load', () => {
    window.localStorage.setItem('quant_lab_auth_token', 'legacy-access');
    window.localStorage.setItem('quant_lab_refresh_token', 'legacy-refresh');

    const { getApiAuthToken, getApiRefreshToken } = require('../services/api');

    expect(getApiAuthToken()).toBe('legacy-access');
    expect(getApiRefreshToken()).toBe('legacy-refresh');
    expect(window.localStorage.getItem('quant_research_auth_token')).toBe('legacy-access');
    expect(window.localStorage.getItem('quant_research_refresh_token')).toBe('legacy-refresh');
    expect(window.localStorage.getItem('quant_lab_auth_token')).toBeNull();
    expect(window.localStorage.getItem('quant_lab_refresh_token')).toBeNull();
  });

  it('writes only current public research token keys', () => {
    const { setApiAuthToken, setApiRefreshToken } = require('../services/api');

    setApiAuthToken('access-token');
    setApiRefreshToken('refresh-token');

    expect(window.localStorage.getItem('quant_research_auth_token')).toBe('access-token');
    expect(window.localStorage.getItem('quant_research_refresh_token')).toBe('refresh-token');
    expect(window.localStorage.getItem('quant_lab_auth_token')).toBeNull();
    expect(window.localStorage.getItem('quant_lab_refresh_token')).toBeNull();

    setApiAuthToken('');
    setApiRefreshToken('');

    expect(window.localStorage.getItem('quant_research_auth_token')).toBeNull();
    expect(window.localStorage.getItem('quant_research_refresh_token')).toBeNull();
  });
});
