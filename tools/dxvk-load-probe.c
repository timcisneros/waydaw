#include <windows.h>
#include <stdio.h>

static int print_last_error(const char *label) {
    DWORD err = GetLastError();
    printf("%s=failed error=%lu\n", label, (unsigned long)err);
    return 1;
}

int main(void) {
    int failed = 0;
    HMODULE dxgi;
    HMODULE d3d11;
    FARPROC create_factory;
    FARPROC create_device;

    SetLastError(0);
    dxgi = LoadLibraryW(L"dxgi.dll");
    if (dxgi) {
        printf("LoadLibraryW_dxgi=ok handle=%p\n", (void *)dxgi);
    } else {
        failed |= print_last_error("LoadLibraryW_dxgi");
    }

    SetLastError(0);
    d3d11 = LoadLibraryW(L"d3d11.dll");
    if (d3d11) {
        printf("LoadLibraryW_d3d11=ok handle=%p\n", (void *)d3d11);
    } else {
        failed |= print_last_error("LoadLibraryW_d3d11");
    }

    SetLastError(0);
    create_factory = dxgi ? GetProcAddress(dxgi, "CreateDXGIFactory1") : NULL;
    if (create_factory) {
        printf("GetProcAddress_CreateDXGIFactory1=ok address=%p\n", (void *)create_factory);
    } else {
        failed |= print_last_error("GetProcAddress_CreateDXGIFactory1");
    }

    SetLastError(0);
    create_device = d3d11 ? GetProcAddress(d3d11, "D3D11CreateDevice") : NULL;
    if (create_device) {
        printf("GetProcAddress_D3D11CreateDevice=ok address=%p\n", (void *)create_device);
    } else {
        failed |= print_last_error("GetProcAddress_D3D11CreateDevice");
    }

    if (d3d11) {
        FreeLibrary(d3d11);
    }
    if (dxgi) {
        FreeLibrary(dxgi);
    }

    return failed ? 1 : 0;
}
