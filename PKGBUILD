# Maintainer: Martin Braun <martin-braun@w9mail.com>
pkgname=t2saild
pkgver=0.1.0
pkgrel=1
pkgdesc="Shell daemon for T2 Mac battery sail control with OpenRC service definition"
arch=('x86_64')
url='https://github.com/martin-braun/t2saild'
license=('GPL3')
depends=('linux-t2' 'findutils' 'util-linux' 'cpupower')
source=('t2saild' 't2saild.initd' 't2saild.confd' 'Makefile')
sha256sums=('SKIP' 'SKIP' 'SKIP' 'SKIP')
backup=('etc/conf.d/t2saild')

package() {
    make DESTDIR="$pkgdir" install
}
